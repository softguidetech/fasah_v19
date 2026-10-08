{
    'name': 'Fasah Bridge - Client',
    'version': '19.0.1.1.0',
    'summary': 'Send to Fasah button on invoices, routed through the Fasah bridge',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
        'data/ir_cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
}
