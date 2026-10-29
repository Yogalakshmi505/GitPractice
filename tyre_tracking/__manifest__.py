{
    'name': 'Tyre Smart Tracking',
    'version': '16.0.1.1.0',
    'summary': 'Tyre tracking from Stock to Scrap with Touch Dashboard and Wheel Alignment screens',
    'category': 'Manufacturing',
    'author': 'Shorepoint Systems',
    'depends': ['base', 'fleet', 'mrp'],
    'data': [
        'security/ir.model.access.csv',
        'views/tyre_dashboard_views.xml',
        'views/tyre_menus.xml',
        'views/tyre_alignment_views.xml',
        'data/alignment_spec_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'tyre_tracking/static/src/css/tyre_dashboard.css',
            'tyre_tracking/static/src/js/tyre_dashboard.js',
            'tyre_tracking/static/src/xml/tyre_dashboard.xml',
            'tyre_tracking/static/src/css/alignment_app.css',
            'tyre_tracking/static/src/js/alignment_app.js',
            'tyre_tracking/static/src/xml/alignment_app.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
