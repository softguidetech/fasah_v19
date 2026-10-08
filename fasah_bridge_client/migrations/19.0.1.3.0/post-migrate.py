from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Upgrade from 19.0.1.1.x: keep single-company databases working as before."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].search([])
    if len(companies) == 1:
        companies.fasah_bridge_enabled = True
