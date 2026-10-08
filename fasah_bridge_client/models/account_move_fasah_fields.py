# FasahPay invoice fields on the client side. Same names as in the FasahPay Connector, so
# _fasah_bridge_payload() sends them to the bridge (the "fasah" block) without extra mapping.
from odoo import fields, models

from .fasah_lookup_data import (
    BROKER_LICENSE_TYPE_SELECTION,
    INVOICE_CATEGORY_SELECTION,
    PAYMENT_METHOD_SELECTION,
    PORT_SELECTION,
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    fasah_invoice_category = fields.Selection(
        INVOICE_CATEGORY_SELECTION, string='FasahPay Category', copy=False,
        help='Empty = the bridge default (General).')
    fasah_payment_method = fields.Selection(
        PAYMENT_METHOD_SELECTION, string='FasahPay Payment Method', copy=False,
        help='Empty = the bridge default (Sadad).')
    fasah_port = fields.Selection(PORT_SELECTION, string='Port', copy=False)

    # Bill of Lading
    fasah_bill_of_lading_no = fields.Char('Bill of Lading No.', copy=False)
    fasah_doc_ref_no = fields.Char('Manifest Doc Ref No.', copy=False,
                                   help='Option A - 14-digit manifest reference.')
    fasah_carrier_manifest = fields.Char('Customs Manifest No.', copy=False,
                                         help='Option B, used with the manifest date.')
    fasah_carrier_manifest_date = fields.Date('Customs Manifest Date', copy=False)
    fasah_transit_declaration = fields.Char('Transit Declaration', copy=False)
    fasah_shipment_type = fields.Integer('Shipment Type (code)', copy=False)

    # Declaration
    fasah_declaration_number = fields.Char('Declaration Number', copy=False)
    fasah_declaration_date = fields.Date('Declaration Date', copy=False)
    fasah_declaration_type = fields.Integer('Declaration Type (code)', copy=False)

    # Importer / Customs Broker / Shipping Agent
    fasah_importer_number = fields.Char('Importer Number', copy=False)
    fasah_customs_broker_license_number = fields.Char('Broker License Number', copy=False)
    fasah_broker_license_type = fields.Selection(
        BROKER_LICENSE_TYPE_SELECTION, string='Broker License Type', copy=False)
    fasah_shipping_agent_number = fields.Char('Shipping Agent Number', copy=False)

    # General + shared
    fasah_company_name = fields.Char('Consumer Company Name (General)', copy=False)
    fasah_company_registration_number = fields.Char('Consumer CR Number (General)', copy=False)
    fasah_bill_number = fields.Char('Bill Number', copy=False)

    # Consumer contact (empty = taken from the customer on the bridge)
    fasah_customer_vat_number = fields.Char('Customer VAT Number', copy=False)
    fasah_consumer_company_name_en = fields.Char('Consumer Name (EN)', copy=False)
    fasah_consumer_company_name_ar = fields.Char('Consumer Name (AR)', copy=False)
    fasah_consumer_email = fields.Char('Consumer Email', copy=False)
    fasah_consumer_mobile = fields.Char('Consumer Mobile', copy=False, help='05XXXXXXXX or 9665XXXXXXXX')
    fasah_consumer_user_id = fields.Char('Consumer User ID', copy=False)
