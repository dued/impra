# -*- coding: utf-8 -*-

from odoo import _, models, fields, api




class UnidadMedidaSunat(models.Model):
	_inherit = 'product.product'

	um_sunat = fields.Many2one('um.sunat')
	
