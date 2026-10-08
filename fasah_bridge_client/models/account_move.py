import datetime
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

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

# FasahPay fields sent to the bridge in the "fasah" block (FasahPay tab on the invoice).
# Empty category = the bridge default (General).
FASAH_FIELDS = [
    'invoice_category', 'payment_method', 'bill_of_lading_no', 'doc_ref_no', 'carrier_manifest',
    'carrier_manifest_date', 'transit_declaration', 'declaration_number', 'declaration_date',
    'declaration_type', 'importer_number', 'customs_broker_license_number', 'broker_license_type',
    'shipping_agent_number', 'company_name', 'company_registration_number', 'bill_number',
    'shipment_type', 'port', 'customer_vat_number', 'consumer_company_name_en',
    'consumer_company_name_ar', 'consumer_email', 'consumer_mobile', 'consumer_user_id',
]

# Fields that belong to one category only - not sent when another category is chosen.
_COMMON = {'invoice_category', 'payment_method', 'customer_vat_number', 'consumer_company_name_en',
           'consumer_company_name_ar', 'consumer_email', 'consumer_mobile', 'consumer_user_id'}
CATEGORY_KEYS = {
    'bill_of_lading': _COMMON | {'bill_of_lading_no', 'doc_ref_no', 'carrier_manifest', 'carrier_manifest_date',
                                 'transit_declaration', 'shipment_type', 'port'},
    'declaration': _COMMON | {'declaration_number', 'declaration_date', 'declaration_type', 'bill_number',
                              'bill_of_lading_no', 'port'},
    'importer': _COMMON | {'importer_number', 'bill_number', 'bill_of_lading_no', 'port'},
    'custom_broker': _COMMON | {'customs_broker_license_number', 'broker_license_type', 'bill_number',
                                'bill_of_lading_no', 'port'},
    'shipping_agent': _COMMON | {'shipping_agent_number', 'bill_number', 'bill_of_lading_no', 'port'},
    'general': _COMMON | {'company_name', 'company_registration_number', 'bill_number'},
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    fasah_bridge_state = fields.Selection(
        STATES, string='Fasah Status', default='not_sent', copy=False, tracking=True)
    fasah_bridge_ref = fields.Char('Fasah Reference', copy=False, readonly=True)
    fasah_bridge_sadad = fields.Char('SADAD Number', copy=False, readonly=True)
    fasah_bridge_message = fields.Text('Fasah Message', copy=False, readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def _fasah_bridge_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        url = (ICP.get_param('fasah_bridge.url') or '').rstrip('/')
        key = ICP.get_param('fasah_bridge.api_key')
        if not url or not key:
            raise UserError(_('Set the system parameters fasah_bridge.url and fasah_bridge.api_key first.'))
        return url, {'Authorization': f'Bearer {key}'}

    def _fasah_bridge_payload(self):
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        partner = self.partner_id.commercial_partner_id
        fasah = {}
        allowed = CATEGORY_KEYS.get(self.fasah_invoice_category or 'general', set(FASAH_FIELDS))             if 'fasah_invoice_category' in self._fields else set(FASAH_FIELDS)
        for key in FASAH_FIELDS:
            if key not in allowed:
                continue
            field = 'fasah_' + key
            if field in self._fields and self[field]:
                value = self[field]
                fasah[key] = fields.Date.to_string(value) if isinstance(value, datetime.date) else value
        return {
            'external_ref': self.name,
            'move_type': self.move_type,
            'invoice_date': fields.Date.to_string(self.invoice_date),
            'due_date': fields.Date.to_string(self.invoice_date_due) if self.invoice_date_due else '',
            'currency': self.currency_id.name,
            'reference': self.ref or '',
            'partner': {
                'name': partner.name,
                'vat': partner.vat or '',
                'country': partner.country_id.code or '',
                'email': partner.email or '',
                'mobile': getattr(partner, 'mobile', False) or partner.phone or '',
                'street': partner.street or '',
                'city': partner.city or '',
                'zip': partner.zip or '',
            },
            'amount_untaxed': self.amount_untaxed,
            'amount_tax': self.amount_tax,
            'amount_total': self.amount_total,
            'lines': [{
                'name': l.name,
                'product_code': l.product_id.default_code or '',
                'quantity': l.quantity,
                'price_unit': l.price_unit,
                'discount': l.discount,
                # first percent tax of the line (FasahPay takes one VAT rate per line)
                'tax_rate': (l.tax_ids.filtered(lambda t: t.amount_type == 'percent')[:1].amount or 0.0),
                'price_subtotal': l.price_subtotal,
                'price_total': l.price_total,
            } for l in lines],
            'fasah': fasah,
        }

    # Same mandatory fields as the FasahPay Connector checks on the bridge side; checked here
    # first so the user gets the message before anything is sent.
    _FASAH_BRIDGE_REQUIRED = {
        'bill_of_lading': [('fasah_bill_of_lading_no', 'Bill of Lading No.'), ('fasah_port', 'Port'),
                           ('fasah_shipment_type', 'Shipment Type')],
        'declaration': [('fasah_declaration_number', 'Declaration Number'),
                        ('fasah_declaration_date', 'Declaration Date'),
                        ('fasah_declaration_type', 'Declaration Type'), ('fasah_port', 'Port')],
        'importer': [('fasah_importer_number', 'Importer Number'), ('fasah_port', 'Port')],
        'custom_broker': [('fasah_customs_broker_license_number', 'Broker License Number'),
                          ('fasah_broker_license_type', 'Broker License Type'), ('fasah_port', 'Port')],
        'shipping_agent': [('fasah_shipping_agent_number', 'Shipping Agent Number'), ('fasah_port', 'Port')],
    }

    def _fasah_bridge_check_required(self):
        self.ensure_one()
        category = self.fasah_invoice_category or 'general'
        missing = [label for fname, label in self._FASAH_BRIDGE_REQUIRED.get(category, []) if not self[fname]]
        partner = self.partner_id.commercial_partner_id
        if category == 'bill_of_lading' and not (
                self.fasah_doc_ref_no or (self.fasah_carrier_manifest and self.fasah_carrier_manifest_date)):
            missing.append('Manifest Doc Ref No. (or Customs Manifest No. + Date)')
        if category in ('general', 'bill_of_lading') and not (self.fasah_consumer_email or partner.email):
            missing.append('Consumer Email (or customer e-mail)')
        if category == 'general' and not (
                self.fasah_consumer_mobile or partner.phone or getattr(partner, 'mobile', False)):
            missing.append('Consumer Mobile (or customer phone)')
        if not (self.fasah_customer_vat_number or partner.vat):
            missing.append('Customer VAT Number')
        if missing:
            raise UserError(_('%(inv)s: fill in these FasahPay fields first (FasahPay tab): %(fields)s',
                              inv=self.name, fields=', '.join(missing)))

    def _fasah_bridge_apply(self, data):
        self.write({
            'fasah_bridge_state': data.get('state') or 'queued',
            'fasah_bridge_ref': data.get('fasah_ref') or False,
            'fasah_bridge_sadad': data.get('sadad_number') or False,
            'fasah_bridge_message': data.get('message') or False,
        })

    # ------------------------------------------------------------------
    def action_send_to_fasah_bridge(self):
        for move in self:
            url, headers = move._fasah_bridge_config()
            if move.state != 'posted':
                raise UserError(_('Only posted invoices can be sent to Fasah.'))
            move._fasah_bridge_check_required()
            try:
                resp = requests.post(f'{url}/fasah_bridge/v1/invoices',
                                     json=move._fasah_bridge_payload(),
                                     headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise UserError(_('Could not reach the Fasah bridge: %s', e))
            if resp.status_code not in (200, 202):
                raise UserError(_('Fasah bridge refused the invoice (%(code)s): %(body)s',
                                  code=resp.status_code, body=resp.text[:500]))
            move._fasah_bridge_apply(resp.json())
            move.message_post(body=_('Invoice sent to the Fasah bridge.'))
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
