from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fasah_bridge_enabled = fields.Boolean(
        'Fasah Bridge Enabled',
        help='Show "Send to Fasah" on this company\'s invoices. Leave off for companies that do not issue FasahPay invoices.')
    fasah_bridge_url = fields.Char(
        'Fasah Bridge URL', help='Leave empty to use the system parameter fasah_bridge.url.')
    fasah_bridge_api_key = fields.Char(
        'Fasah Bridge API Key', groups='base.group_system',
        help='Leave empty to use the system parameter fasah_bridge.api_key.')
