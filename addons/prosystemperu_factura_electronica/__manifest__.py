# -*- coding: utf-8 -*-
{
    'name': "Factura electronica",

    'summary': """Agrega campos a la factura""",

    'description': """
        Configurar un diario(journal para cada comprobante)
    """,

    'author': "Prosystem",
    'website': "http://www.contasql.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','account_invoicing','prosystemperu_reporte_crystalreport','prosystemperu_company','inputmask_widget'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'wizard/wizard_cpe.xml',
        'wizard/wizard_anulacion.xml',
        'views/documentos_relacionados.xml',
        'data/documentos_relacionados_data.xml',
        'views/tipo_documento.xml',
        'data/tipo_documento_data.xml',
        'views/motivo_rectificativa.xml',
        'views/motivo_debito.xml',
        'data/motivo_rectificativa_data.xml',
        'data/motivo_debito_data.xml',        
        'views/um_sunat.xml',
        'data/um_sunat_data.xml',
        'views/herencia_producto.xml',
        'views/tipo_afectacion_igv.xml',
        'views/tipo_operacion.xml',
        'data/codigo_tipo_tributo_data.xml',
        'data/tipo_afectacion_igv_data.xml',
        'data/tipo_operacion_data.xml',
        'views/currency_herencia.xml',
        'views/usuario_herencia.xml',
        'views/factura_refund_herencia.xml',
        'views/factura_herencia.xml',       
        'report/reporte_herencia_invoice_qr.xml',
        'views/boleta_resumen.xml',        
        'views/factura_compras_herencia.xml',        
        'views/factura_baja.xml',
        'views/boleta_resumen_baja.xml',
        'views/journal_herencia.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}