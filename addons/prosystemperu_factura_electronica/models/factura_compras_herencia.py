# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class FacturaComprasHerencia(models.Model):
	_inherit='account.invoice'

	tip_doc_compra = fields.Many2one('tipo.documento')
	serie_compra = fields.Char()
	numeracion_compra = fields.Char()

	_sql_constraints = [('fac_compras_correla_uniq', 'unique(partner_id,tip_doc_compra,serie_compra,numeracion_compra)', 'los campos deben ser unicos!'),]	
	
	@api.onchange('tip_doc_compra','serie_compra','numeracion_compra')
	def onchange_numeracion(self):
		
		if not self.tip_doc_compra:
			return
		if not self.serie_compra:
			return
		if not self.numeracion_compra:
			return

		tipo_documento = ""	
		if not self.tip_doc_compra.abreviatura:
			tipo_documento = self.tip_doc_compra.code
		else:
			tipo_documento = self.tip_doc_compra.abreviatura
		self.reference = tipo_documento + "/" + self.serie_compra + "-" + self.numeracion_compra