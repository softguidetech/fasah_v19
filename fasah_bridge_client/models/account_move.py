import json
import logging
import re

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .fasah_lookup_data import BROKER_LICENSE_TYPE_SELECTION, PORT_SELECTION

_logger = logging.getLogger(__name__)

TIMEOUT = 30

STATES = [
    ('not_sent', 'Not Sent'),
    ('queued', 'In Queue'),
    ('sent', 'Sent to Fasah'),
    ('accepted', 'Accepted'),
    ('paid', 'Paid'),
    ('cancelled', 'Cancelled'),
    ('rejected', 'Rejected'),
    ('error', 'Error'),
]

# ----------------------------------------------------------------------
# FasahPay rules (FasahPay API 2.0.0 + Integration Guidelines v3.0 + rejections seen live).
# The invoice is built here in FasahPay's own format and checked against these rules;
# the bridge server only forwards it with its credentials / whitelisted IP.
# ----------------------------------------------------------------------
ENDPOINTS = {
    'general': '/',
    'bill_of_lading': '/billoflading',
    'declaration': '/declaration',
    'importer': '/importer',
    'custom_broker': '/custombroker',
    'shipping_agent': '/shippingagent',
}
PAYMENT_METHODS = ('Sadad', 'View')
SHIPMENT_TYPES = (1, 2, 3, 4, 5, 9, 11, 12, 15, 16, 98, 99)
DECLARATION_TYPES = SHIPMENT_TYPES
LICENSE_TYPES = tuple(code for code, _label in BROKER_LICENSE_TYPE_SELECTION)
PORTS = tuple(code for code, _label in PORT_SELECTION)
VAT_RATES = (0.0, 15.0)
MIN_GRAND_TOTAL = 25.0  # SAR - FasahPay refuses smaller invoices
VAT_RE = re.compile(r'^3\d{13}3$')  # Saudi VAT: 15 digits, starts and ends with 3
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')
INTERNAL_NO_RE = re.compile(r'^[A-Za-z0-9/_\-]{1,50}$')


def _clean_vat(vat):
    value = (vat or '').strip()
    if value.upper().startswith('SA'):
        value = value[2:]
    return ''.join(ch for ch in value if ch.isdigit())


def _clean_mobile(mobile):
    """05XXXXXXXX or 9665XXXXXXXX, else '' (reported by the check)."""
    digits = ''.join(ch for ch in (mobile or '') if ch.isdigit())
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('9665') and len(digits) == 12:
        return digits
    if digits.startswith('05') and len(digits) == 10:
        return digits
    if digits.startswith('5') and len(digits) == 9:
        return '0' + digits
    return ''


class AccountMove(models.Model):
    _inherit = 'account.move'

    fasah_bridge_state = fields.Selection(
        STATES, string='Fasah Status', default='not_sent', copy=False, tracking=True)
    fasah_bridge_ref = fields.Char('Fasah Reference', copy=False, readonly=True)
    fasah_bridge_sadad = fields.Char('SADAD Number', copy=False, readonly=True)
    fasah_bridge_message = fields.Text('Fasah Message', copy=False, readonly=True)
    fasah_bridge_request = fields.Text(
        'FasahPay Request', copy=False, readonly=True,
        help='The exact invoice sent to FasahPay (built and checked on this database).')

    # ------------------------------------------------------------------
    @api.model
    def _fasah_bridge_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        url = (ICP.get_param('fasah_bridge.url') or '').rstrip('/')
        key = ICP.get_param('fasah_bridge.api_key')
        if not url or not key:
            raise UserError(_('Set the system parameters fasah_bridge.url and fasah_bridge.api_key first.'))
        return url, {'Authorization': f'Bearer {key}'}

    # ------------------------------------------------------------------
    # Build the FasahPay invoice (same format as the FasahPay Connector)
    # ------------------------------------------------------------------
    def _fasah_bridge_internal_number(self):
        value = (self.name or '').strip()
        if not value.isascii():
            value = 'INV' + re.sub(r'[^A-Za-z0-9]', '', value)
        return value

    def _fasah_bridge_name_in(self, record, lang):
        """record.name in `lang`, or in the current language when `lang` is not installed."""
        if not record:
            return ''
        installed = [code for code, _name in self.env['res.lang'].get_installed()]
        return (record.with_context(lang=lang) if lang in installed else record).name or ''

    def _fasah_bridge_lines(self):
        return self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

    def _fasah_bridge_items(self):
        items = []
        for seq, line in enumerate(self._fasah_bridge_lines(), start=1):
            qty = line.quantity
            price = line.price_unit
            line_amount = round(price * qty, 2)
            discount_pct = line.discount or 0.0
            discount_amount = round(line_amount * discount_pct / 100.0, 2)
            after_discount = round(line_amount - discount_amount, 2)
            percent_taxes = line.tax_ids.filtered(lambda t: t.amount_type == 'percent')
            vat_rate = percent_taxes[:1].amount if percent_taxes else 0.0
            total_vat = round(after_discount * vat_rate / 100.0, 2)
            uom_en = self._fasah_bridge_name_in(line.product_uom_id, 'en_US')
            uom_ar = self._fasah_bridge_name_in(line.product_uom_id, 'ar_001')
            items.append({
                'invoiceLineSerialNo': seq,
                'itemCode': line.product_id.default_code or 'ITEM-%s' % seq,
                'itemDescriptionArabic': (line.name or line.product_id.name or '').strip(),
                'itemDescriptionEnglish': (self._fasah_bridge_name_in(line.product_id, 'en_US')
                                           or line.name or '').strip(),
                'unitOfMeasureArabic': uom_ar or 'وحدة',
                'unitOfMeasureEnglish': uom_en or 'Unit',
                'itemPrice': price,
                'quantity': qty,
                'lineItemAmount': line_amount,
                'lineItemDiscount': discount_pct,
                'lineItemDiscountAmount': discount_amount,
                'lineItemAmountAfterDiscount': after_discount,
                'lineItemVAT': vat_rate,
                'lineItemTotalVAT': total_vat,
                'lineItemTotal': round(after_discount + total_vat, 2),
            })
        return items

    def _fasah_bridge_build(self):
        """Returns (endpoint, body) exactly as FasahPay expects them."""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        category = self.fasah_invoice_category or 'general'
        items = self._fasah_bridge_items()
        before_vat = round(sum(i['lineItemAmountAfterDiscount'] for i in items), 2)
        total_vat = round(sum(i['lineItemTotalVAT'] for i in items), 2)
        email = (self.fasah_consumer_email or partner.email or '').strip()
        mobile_raw = self.fasah_consumer_mobile or partner.phone or getattr(partner, 'mobile', False) or ''
        body = {
            'internalInvoiceNumber': self._fasah_bridge_internal_number(),
            'paymentMethod': self.fasah_payment_method or 'Sadad',
            'invoiceIssueDate': fields.Date.to_string(self.invoice_date),
            'invoiceDueDate': fields.Date.to_string(self.invoice_date_due or self.invoice_date),
            'invoiceDescription': (self.ref or self.name or 'Invoice').strip(),
            'billerVATNumber': _clean_vat(self.company_id.vat),
            'customerVATNumber': _clean_vat(self.fasah_customer_vat_number or partner.vat),
            'totalBeforeVAT': before_vat,
            'totalVAT': total_vat,
            'grandTotal': round(before_vat + total_vat, 2),
            'item': items,
        }
        if category == 'general':
            body.update({
                'companyName': (self.fasah_company_name or partner.name or '').strip(),
                'consumerEmail': email,
                'consumerMobile': _clean_mobile(mobile_raw),
            })
            if self.fasah_company_registration_number:
                body['companyRegistrationNumber'] = self.fasah_company_registration_number.strip()
        else:
            body['port'] = self.fasah_port or ''
            if self.fasah_bill_number and category != 'bill_of_lading':
                body['billNumber'] = self.fasah_bill_number.strip()
            if self.fasah_bill_of_lading_no:
                body['billofLadingNo'] = self.fasah_bill_of_lading_no.strip()
        if category == 'bill_of_lading':
            body['shipmentType'] = self.fasah_shipment_type
            if self.fasah_doc_ref_no:
                body['docRefNo'] = self.fasah_doc_ref_no.strip()
            if self.fasah_carrier_manifest:
                body['carrierManifest'] = self.fasah_carrier_manifest.strip()
            if self.fasah_carrier_manifest_date:
                body['carrierManifestDate'] = fields.Date.to_string(self.fasah_carrier_manifest_date)
            if self.fasah_transit_declaration:
                body['transitDeclaration'] = self.fasah_transit_declaration.strip()
            body['consumerContactDetails'] = {
                'companyNameEn': (self.fasah_consumer_company_name_en or partner.name or '').strip(),
                'companyNameAr': (self.fasah_consumer_company_name_ar or '').strip(),
                'consumerEmail': email,
                'consumerMobile': _clean_mobile(mobile_raw),
                'consumerUserId': self.fasah_consumer_user_id or partner.ref or str(partner.id),
            }
        elif category == 'declaration':
            body.update({
                'declarationNumber': (self.fasah_declaration_number or '').strip(),
                'declarationDate': fields.Date.to_string(self.fasah_declaration_date) if self.fasah_declaration_date else '',
                'declarationType': self.fasah_declaration_type,
            })
        elif category == 'importer':
            body['importerNumber'] = (self.fasah_importer_number or '').strip()
        elif category == 'custom_broker':
            body.update({
                'customsBrokerLicenseNumber': (self.fasah_customs_broker_license_number or '').strip(),
                'licenseType': self.fasah_broker_license_type or '',
            })
        elif category == 'shipping_agent':
            body['shippingAgentNumber'] = (self.fasah_shipping_agent_number or '').strip()
        return ENDPOINTS[category], body

    # ------------------------------------------------------------------
    # Check the invoice against FasahPay's rules - every problem at once
    # ------------------------------------------------------------------
    def _fasah_bridge_problems(self):
        self.ensure_one()
        p = []
        partner = self.partner_id.commercial_partner_id
        category = self.fasah_invoice_category or 'general'

        # the invoice itself
        if self.move_type != 'out_invoice':
            p.append(_('Only customer invoices can be sent to FasahPay (not credit notes or bills).'))
        if self.state != 'posted':
            p.append(_('Confirm (post) the invoice first.'))
        if self.currency_id.name != 'SAR':
            p.append(_('FasahPay accepts invoices in SAR only (this invoice is in %s).', self.currency_id.name))
        if not self.invoice_date:
            p.append(_('Invoice Date is missing.'))
        elif self.invoice_date_due and self.invoice_date_due < self.invoice_date:
            p.append(_('Due Date is before the Invoice Date.'))
        internal_no = self._fasah_bridge_internal_number()
        if not INTERNAL_NO_RE.match(internal_no or ''):
            p.append(_('Invoice number "%s" must be Latin letters/digits (max 50).', internal_no))
        if self.fasah_payment_method and self.fasah_payment_method not in PAYMENT_METHODS:
            p.append(_('Payment Method must be Sadad or View.'))

        # biller (this company) and customer
        biller_vat = _clean_vat(self.company_id.vat)
        if not VAT_RE.match(biller_vat):
            p.append(_('Your company VAT number "%s" is not a valid 15-digit Saudi VAT (Settings > Companies). '
                       'It must not be the CR number.', self.company_id.vat or ''))
        customer_vat = _clean_vat(self.fasah_customer_vat_number or partner.vat)
        if not customer_vat:
            p.append(_('Customer VAT Number is missing (customer or FasahPay tab).'))
        elif not VAT_RE.match(customer_vat):
            p.append(_('Customer VAT Number "%s" is not a valid 15-digit Saudi VAT (starts and ends with 3).',
                       customer_vat))
        elif customer_vat == biller_vat:
            p.append(_('Customer VAT Number is the same as your own company VAT.'))

        email = (self.fasah_consumer_email or partner.email or '').strip()
        mobile_raw = self.fasah_consumer_mobile or partner.phone or getattr(partner, 'mobile', False) or ''
        needs_contact = category in ('general', 'bill_of_lading')
        if needs_contact:
            if not email:
                p.append(_('Consumer Email is missing (customer or FasahPay tab).'))
            elif not EMAIL_RE.match(email):
                p.append(_('Consumer Email "%s" is not valid - one e-mail address only.', email))
        if category == 'general':
            if not mobile_raw:
                p.append(_('Consumer Mobile is missing (customer phone or FasahPay tab).'))
            elif not _clean_mobile(mobile_raw):
                p.append(_('Consumer Mobile "%s" is not a Saudi mobile. Use 05XXXXXXXX or 9665XXXXXXXX.', mobile_raw))
            if not (self.fasah_company_name or partner.name):
                p.append(_('Consumer Company Name is missing.'))
        elif category == 'bill_of_lading' and mobile_raw and not _clean_mobile(mobile_raw):
            p.append(_('Consumer Mobile "%s" is not a Saudi mobile. Use 05XXXXXXXX or 9665XXXXXXXX.', mobile_raw))

        # category fields
        if category != 'general':
            if not self.fasah_port:
                p.append(_('Port is missing.'))
            elif self.fasah_port not in PORTS:
                p.append(_('Port "%s" is not a FasahPay port code.', self.fasah_port))
        if category == 'bill_of_lading':
            if not self.fasah_bill_of_lading_no:
                p.append(_('Bill of Lading No. is missing.'))
            if self.fasah_shipment_type not in SHIPMENT_TYPES:
                p.append(_('Shipment Type must be one of %s.', ', '.join(map(str, SHIPMENT_TYPES))))
            doc_ref = (self.fasah_doc_ref_no or '').strip()
            if doc_ref and not (doc_ref.isdigit() and len(doc_ref) == 14):
                p.append(_('Manifest Doc Ref No. must be 14 digits.'))
            if not doc_ref and not (self.fasah_carrier_manifest and self.fasah_carrier_manifest_date):
                p.append(_('Enter the Manifest Doc Ref No. (14 digits) or the Customs Manifest No. + Date.'))
            if not (self.fasah_consumer_company_name_en or partner.name):
                p.append(_('Consumer Name (EN) is missing.'))
        elif category == 'declaration':
            if not self.fasah_declaration_number:
                p.append(_('Declaration Number is missing.'))
            if not self.fasah_declaration_date:
                p.append(_('Declaration Date is missing.'))
            elif self.fasah_declaration_date > fields.Date.context_today(self):
                p.append(_('Declaration Date is in the future.'))
            if self.fasah_declaration_type not in DECLARATION_TYPES:
                p.append(_('Declaration Type must be one of %s.', ', '.join(map(str, DECLARATION_TYPES))))
        elif category == 'importer':
            if not self.fasah_importer_number:
                p.append(_('Importer Number is missing.'))
            elif not self.fasah_importer_number.strip().isdigit():
                p.append(_('Importer Number must be digits only.'))
        elif category == 'custom_broker':
            if not self.fasah_customs_broker_license_number:
                p.append(_('Broker License Number is missing.'))
            if self.fasah_broker_license_type not in LICENSE_TYPES:
                p.append(_('Broker License Type is missing.'))
        elif category == 'shipping_agent':
            if not self.fasah_shipping_agent_number:
                p.append(_('Shipping Agent Number is missing.'))

        # lines and totals
        lines = self._fasah_bridge_lines()
        if not lines:
            p.append(_('The invoice has no lines.'))
        for n, line in enumerate(lines, start=1):
            label = _('Line %(n)s (%(name)s)', n=n, name=(line.name or '')[:30])
            if not (line.name or line.product_id.name or '').strip():
                p.append(_('%s: description is empty.', label))
            if line.quantity <= 0:
                p.append(_('%s: quantity must be above zero.', label))
            if line.price_unit <= 0:
                p.append(_('%s: unit price must be above zero.', label))
            if not 0 <= (line.discount or 0) < 100:
                p.append(_('%s: discount must be between 0 and 100%%.', label))
            taxes = line.tax_ids
            if len(taxes) > 1:
                p.append(_('%s: FasahPay takes one VAT per line - this line has %s taxes.', label, len(taxes)))
            for tax in taxes:
                if tax.amount_type != 'percent':
                    p.append(_('%(l)s: tax "%(t)s" is not a percentage tax.', l=label, t=tax.name))
                elif tax.price_include:
                    p.append(_('%(l)s: tax "%(t)s" is price-included; use a tax excluded from the price.',
                               l=label, t=tax.name))
                elif tax.amount not in VAT_RATES:
                    p.append(_('%(l)s: VAT %(r)s%% is not accepted (0%% or 15%% only).', l=label, r=tax.amount))

        if lines and not p:
            _endpoint, body = self._fasah_bridge_build()
            # FasahPay's totals must match this invoice, otherwise the customer pays a different amount
            for key, odoo_value, name in (('totalBeforeVAT', self.amount_untaxed, _('Untaxed amount')),
                                          ('totalVAT', self.amount_tax, _('VAT')),
                                          ('grandTotal', self.amount_total, _('Total'))):
                if abs(body[key] - odoo_value) > 0.01:
                    p.append(_('%(name)s on FasahPay would be %(f).2f but the invoice shows %(o).2f '
                               '(rounding/discount). Adjust the lines.', name=name, f=body[key], o=odoo_value))
            if body['grandTotal'] < MIN_GRAND_TOTAL:
                p.append(_('FasahPay minimum invoice total is %(min).2f SAR (this one is %(t).2f).',
                           min=MIN_GRAND_TOTAL, t=body['grandTotal']))
        return p

    def _fasah_bridge_check(self):
        """Raise one message listing everything to fix; return (endpoint, body) when ready."""
        self.ensure_one()
        problems = self._fasah_bridge_problems()
        if problems:
            raise UserError(_('%(inv)s cannot be sent to FasahPay yet. Fix these first:\n\n%(list)s',
                              inv=self.name or '', list='\n'.join('• ' + x for x in problems)))
        return self._fasah_bridge_build()

    def action_check_fasah_bridge(self):
        for move in self:
            endpoint, body = move._fasah_bridge_check()
            move.fasah_bridge_request = json.dumps({'endpoint': endpoint, 'body': body}, ensure_ascii=False, indent=2)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ready for FasahPay'),
                'message': _('All FasahPay checks passed. You can send the invoice.'),
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    def _fasah_bridge_apply(self, data):
        self.write({
            'fasah_bridge_state': data.get('state') or 'queued',
            'fasah_bridge_ref': data.get('fasah_ref') or False,
            'fasah_bridge_sadad': data.get('sadad_number') or False,
            'fasah_bridge_message': data.get('message') or False,
        })

    def action_send_to_fasah_bridge(self):
        for move in self:
            url, headers = move._fasah_bridge_config()
            endpoint, body = move._fasah_bridge_check()
            move.fasah_bridge_request = json.dumps({'endpoint': endpoint, 'body': body}, ensure_ascii=False, indent=2)
            try:
                resp = requests.post(f'{url}/fasah_bridge/v1/invoices',
                                     json={'external_ref': move.name, 'endpoint': endpoint, 'body': body},
                                     headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise UserError(_('Could not reach the Fasah bridge: %s', e))
            if resp.status_code not in (200, 202):
                raise UserError(_('Fasah bridge refused the invoice (%(code)s): %(body)s',
                                  code=resp.status_code, body=resp.text[:500]))
            move._fasah_bridge_apply(resp.json())
            move.message_post(body=_('Invoice checked and sent to the Fasah bridge.'))
        return True

    def action_refresh_fasah_bridge_status(self):
        for move in self:
            url, headers = move._fasah_bridge_config()
            try:
                resp = requests.get(f'{url}/fasah_bridge/v1/invoices/status',
                                    params={'external_ref': move.name},
                                    headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise UserError(_('Could not reach the Fasah bridge: %s', e))
            if resp.status_code == 200:
                move._fasah_bridge_apply(resp.json())
        return True

    @api.model
    def _cron_refresh_fasah_status(self, limit=100):
        moves = self.search([('fasah_bridge_state', 'in', ('queued', 'sent', 'accepted'))], limit=limit)
        for move in moves:
            try:
                move.action_refresh_fasah_bridge_status()
            except Exception:  # noqa: BLE001
                _logger.exception('Fasah bridge: status refresh failed for %s', move.name)
