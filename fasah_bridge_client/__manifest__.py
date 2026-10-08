{
    'name': 'Fasah Bridge - Client',
    'version': '19.0.1.2.0',
    'summary': 'Send to Fasah button on invoices, routed through the Fasah bridge',
    'category': 'Accounting',
    'author': 'Ahmed Mohammed Ali Bilal Osman',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
        'data/ir_cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
}
