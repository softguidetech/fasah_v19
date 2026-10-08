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

# Optional FasahPay fields sent to the bridge when this database also has the FasahPay Connector
# installed (same field names, "fasah_" prefix). Without it the bridge uses its defaults (General).
FASAH_FIELDS = [
    'invoice_category', 'payment_method', 'bill_of_lading_no', 'doc_ref_no', 'carrier_manifest',
    'carrier_manifest_date', 'transit_declaration', 'declaration_number', 'declaration_date',
    'declaration_type', 'importer_number', 'customs_broker_license_number', 'broker_license_type',
    'shipping_agent_number', 'company_name', 'company_registration_number', 'bill_number',
    'shipment_type', 'port', 'customer_vat_number', 'consumer_company_name_en',
    'consumer_company_name_ar', 'consumer_email', 'consumer_mobile', 'consumer_user_id',
]


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
        for key in FASAH_FIELDS:
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

    def _fasah_bridge_apply(self, data):
        self.write({
            'fasah_bridge_state': data.get('state') or 'queued',
            'fasah_bridge_ref': data.get('fasah_ref') or False,
            'fasah_bridge_sadad': data.get('sadad_number') or False,
            'fasah_bridge_message': data.get('message') or False,
        })

    # ------------------------------------------------------------------
    def action_send_to_fasah_bridge(self):
        url, headers = self._fasah_bridge_config()
        for move in self:
            if move.state != 'posted':
                raise UserError(_('Only posted invoices can be sent to Fasah.'))
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
        url, headers = self._fasah_bridge_config()
        for move in self:
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
