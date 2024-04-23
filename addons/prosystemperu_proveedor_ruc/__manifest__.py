# -*- coding: utf-8 -*-
{
    'name': "Consultar RUC",

    'summary': 'Agrega la busqueda del ruc y dni ',
    'description': """Agrega campo Ruc""",

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
        'views/departamento_herencia.xml',
        'views/res_provincia.xml',
        'views/res_distrito.xml',
        'views/ruc.xml',
        'data/ubigeo_data.xml',
        'data/country_modifica_data.xml',        
        
        
        
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}