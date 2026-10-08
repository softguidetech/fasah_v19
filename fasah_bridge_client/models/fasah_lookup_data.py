# -*- coding: utf-8 -*-
# Copyright 2026 Ahmed Mohammed Ali Bilal Osman
# License OPL-1 (see LICENSE file for full copyright and licensing details).
"""Static FasahPay lookup tables, transcribed from ELM's
'Invoice Field Descriptions - All (API)' workbook, Lookup Values sheet.

Only Port and Broker License Type are exposed as Selection fields on
account.move - both are complete, unambiguous lists there. Shipment Type
and Declaration Type are left as plain integers on account.move: the
source workbook's own "Shipment Types" table only labels 4 of the 12
codes the API's shipmentType enum actually allows, and its "Declaration
Types" table assigns code 15 to two different labels ("GCC Statistical
Declaration" and "Import from GCC origin"). Rather than silently pick
one, PORT_LOOKUP_REFERENCE / DECLARATION_TYPE_REFERENCE below are kept
as plain reference tuples for a help panel - confirm the exact code
with ELM/the Fasah Pay Operations team before relying on either field.
"""

# (port_no, name_en, name_ar)
PORT_LOOKUP = [
    (10, "JEDDAH ISLAMIC PORT CUSTOMS", "جمرك ميناء جده الاسلامي"),
    (17, "YANBU SEA PORT COMER.", "جمرك ميناء ينبع التجاري"),
    (19, "YANBU SEA PORT INDUS.", "جمرك ميناء الملك فهد الصناعي"),
    (30, "KING ABDULAIZ PORT CUSTOMS", "جمرك ميناء الملك عبدالعزيز"),
    (32, "RAS TANOURA PORT", "جمرك ميناء رأس تنوره"),
    (33, "RAS AL KHAIR SEA PORT", "جمرك رأس الخير"),
    (42, "JUBAIL SEA PORT", "جمرك ميناء الجبيل"),
    (43, "RAS MISHA'AB CUSTOMS", "جمرك راس مشعاب"),
    (45, "JUBAIL SEA PORT INDUSTRIAL", "جمرك ميناء الجبيل الصناعي"),
    (53, "DHIBA PORT CUSTOMS", "جمرك ميناء ضباء"),
    (60, "JIZAN PORT CUSTOMS", "جمرك ميناء جيزان"),
    (75, "KING ABDULLAH SEA PORT", "جمرك ميناء الملك عبد الله"),
    (96, "RABIGH PORT CUSTOMS", "جمرك ميناء رابغ"),
    (34, "RIYADH DRY PORT CUSTOMS", "جمرك الرياض - الميناء الجاف"),
    (31, "BATEHA'A CUSTOMS", "جمرك البطحاء"),
    (35, "AL-ROQA'I CUSTOMS", "جمرك الرقعي"),
    (36, "AL-ODAID CUSTOMS", "جمرك العديد"),
    (41, "SALWA CUSTOMS", "جمرك سلوى"),
    (44, "AL KHAFJI CUSTOMS", "جمرك الخفجي"),
    (51, "HALAT AMMAR CUSTOMS", "جمرك حالة عمار"),
    (54, "AL DORRAH CUSTOMS", "جمرك الدره"),
    (61, "AL TOUWAL CUSTOMS", "جمرك الطوال"),
    (62, "AL MAWSIM CUSTOMS", "جمرك الموسم"),
    (63, "AL KHOBAH CUSTOMS", "جمرك الخوبة"),
    (66, "AL WADIEAH CUSTOMS", "جمرك الوديعة"),
    (67, "ALAB CUSTOMS", "جمرك علب"),
    (69, "AL KHADRA CUSTOMS", "جمرك الخضراء"),
    (83, "KING FAHAD BRIDGE CUSTOMS", "جمرك جسر الملك فهد"),
    (84, "FARASAN CUSTOMS", "جمرك فرسان"),
    (90, "JADEEDAT ARA'AR CUSTOMS", "جمرك جديدة عرعر"),
    (91, "TRAIFF CUSTOMS", "جمرك طريف"),
    (95, "AL HADEETHAH CUSTOMS", "جمرك الحديثة"),
    (100, "HAEL AIRPORT", "جمرك مطار حائل"),
    (11, "KING ABDULAZIZ INTERNATIONAL AIRPORT CUSTOMS", "جمرك مطارالملك عبدالعزيزالدولي"),
    (12, "NAJRAN AIR PORT", "جمرك مطار نجران"),
    (13, "NEOM AIRPORT", "جمرك مطار نيوم"),
    (14, "PRINCE SULTAN AIR BASE CUSTOMS", "جمرك قاعدة الأمير سلطان الجوية"),
    (18, "YANBU AIR PORT", "جمرك مطار ينبع"),
    (20, "KING FAHAD INTERNATIONAL AIRPORT CUSTOMS", "جمرك مطار الملك فهد الدولي"),
    (21, "PRINCE MOHAMMED BIN ABDULAZIZ AIRPORT", "مطار الأمير محمد بن عبدالعزيز"),
    (22, "QASIM AIRPORT CUSTOMS", "جمرك مطار القصيم"),
    (23, "KING KHALED INTERNATIONAL AIRPORT CUSTOMS", "جمرك مطار الملك خالد الدولي"),
    (24, "TAIF AIRPORT CUSTOMS", "جمرك مطار الطائف"),
    (25, "HAEL AIRPORT", "جمرك مطار حائل"),
    (29, "ALAHSA'A INTERNATIONAL AIRPORT CUSTOMS", "جمرك مطار الأحساء الدولي"),
    (50, "TABOUK AIRPORT CUSTOMS", "جمرك مطار تبوك"),
    (64, "JAZAN AIRPORT", "مطار جازان"),
    (71, "ABHA AIRPORT CUSTOMS", "جمرك مطار أبها"),
    (72, "SHARORAH AIRPORT CUSTOMS", "جمرك مطار شروره"),
    (94, "AL JOUF AIRPORT CUSTOMS", "جمرك مطار الجوف"),
    (26, "POSTAL PACKAGES CUSTOMS IN JEDDAH", "جمرك الطرود البريدية بجدة"),
    (27, "POSTAL PACKAGES CUSTOMS IN MADINAH", "جمرك الطرود البريدية بالمدينة"),
    (28, "RIYADH POST CUSTOMS", "جمرك الرياض للبريد"),
    (38, "POSTAL PACKAGES CUSTOMS IN DAMMAM", "جمرك الطرود البريدية بالدمام"),
    (46, "POSTAL PACKAGES CUSTOMS IN MAKKAH", "جمرك الطرود البريدية بمكة"),
]

PORT_SELECTION = [
    (str(code), "%s - %s" % (code, name_en)) for code, name_en, _ in PORT_LOOKUP
]

BROKER_LICENSE_TYPE_SELECTION = [
    ("1", "Government Broker"),
    ("2", "General Broker"),
    ("5", "Customs Clearance Company"),
]

PAYMENT_METHOD_SELECTION = [
    ("Sadad", "Sadad (real bill, subscribed billers)"),
    ("View", "View (demo/testing only, no real SADAD bill)"),
]

INVOICE_CATEGORY_SELECTION = [
    ("bill_of_lading", "Bill of Lading"),
    ("declaration", "Declaration"),
    ("importer", "Importer"),
    ("custom_broker", "Customs Broker"),
    ("shipping_agent", "Shipping Agent"),
    ("general", "General"),
]

FASAH_STATUS_SELECTION = [
    ("not_sent", "Not Sent"),
    ("sent", "Sent"),
    ("waiting", "Waiting for Declaration"),
    ("unpaid", "Unpaid"),
    ("paid", "Paid"),
    ("view", "Viewed (demo)"),
    ("cancelled", "Cancelled"),
    ("error", "Error"),
]

# Reference only (not a Selection - see the module docstring above for why).
# (code, label)
DECLARATION_TYPE_REFERENCE = [
    (1, "Import"),
    (2, "Direct Import"),
    (3, "Export"),
    (4, "Re-export"),
    (5, "Oil export"),
    (6, "Personal Export"),
    (8, "Statiscal Transit"),
    (9, "Export Bonded Area"),
    (13, "Statiscal Transit"),
    (15, "GCC Statistical Declaration / Import from GCC origin (conflicting in source table - confirm with ELM)"),
    (11, "Import from Non GCC origin"),
    (12, "Export from Non GCC origin"),
    (16, "Export from GCC origin"),
    (98, "Export Bonded Area from Non-GCC Origin"),
    (99, "Export Bonded Area from GCC Origin"),
]

# The workbook's "Shipment Types" table only names 4 of the 12 codes the
# shipmentType enum in the API allows (1,2,3,4,5,9,11,12,15,16,98,99).
SHIPMENT_TYPE_REFERENCE = [
    (1, "Import"),
    (2, "Export"),
    (3, "Oil"),
    (4, "Transshipment Import"),
]
