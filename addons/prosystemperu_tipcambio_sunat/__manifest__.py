# -*- coding: utf-8 -*-
{
    'name': "Consulta Tipo de cambio Sunat",

    'summary': """Actualiza el tipo de cambio segun Sunat""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Prosystem",
    'website': "http://www.contasql.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}