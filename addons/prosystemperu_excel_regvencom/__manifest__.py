# -*- coding: utf-8 -*-
{
    'name': "En el modulo de Factuación, agrega un menú en la pestaña informes",

    'summary': """Genera archivos de ventas y compras en excel para ser descargados por el modulo prosystemperu_excel""",

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
    'depends': ['base','prosystemperu_factura_electronica','prosystemperu_excel'],

    # always loaded
    'data': [
        #'security/ir.model.access.csv',        
        'wizard/factura_regventas.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}