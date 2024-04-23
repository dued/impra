# -*- coding: utf-8 -*-

from odoo import api, fields, models
from datetime import datetime
from odoo.exceptions import UserError, ValidationError


class WizardCpe(models.TransientModel):
	_name = 'wizard.cpe'

	def _default_fecha(self):
		context = dict(self._context or {})
		return self.env['factura.baja'].browse(context.get('active_ids')).fecha_doc   

	fecha_consulta=fields.Date(default=_default_fecha)
	detalle_cpe = fields.One2many('wizard.cpe.line','cpe_id')

	@api.onchange('fecha_consulta')
	def _agrega_invoice_detalle(self):
		if not self.fecha_consulta:
			self.fac_baja_linea = False	

		ids_invoice = self.env['account.invoice'].search([('date_invoice','=', self.fecha_consulta),('state','=', 'anulado'),('estado_invoice_xml','=', 'aceptado')], order="id asc")
		
		result = []
		numeracion = 0
		for line in ids_invoice:
			numeracion += 1
			result.append((0, 0, {'capturar': False,'item': numeracion,'id_doc': line.id,'tipo_doc': line.tipo_doc, 'serie_doc': line.serie, 'numeracion_doc': line.numeracion}))
		self.detalle_cpe = result

	def enviar_registro(self):
		lista = []
		ids_fac_baja = []
		numeracion = 0
		context = dict(self._context or {})
		data = self.env['factura.baja'].browse(context.get('active_ids'))

		for baja in data.fac_baja_linea:
			numeracion += 1
			ids_fac_baja.append(baja.id_factura.id)


		for linea in self.detalle_cpe:
			if linea.capturar == True:
				if linea.id_doc.id not in (ids_fac_baja):
					numeracion += 1
					lista.append((0,0 , {'item': numeracion,'id_factura': linea.id_doc.id,'motivo_fac_baja': data.motivo_baja ,'tipo_documento': linea.id_doc.tipo_doc, 'serie_documento': linea.id_doc.serie, 'numeracion_documento': linea.id_doc.numeracion,'fecha_emision_documento': linea.id_doc.date_invoice,'importe_total': linea.id_doc.amount_total }))
						
		for baja in data:						
			baja.fac_baja_linea = lista
			


		

    
    
   
class WizardCpeLine(models.TransientModel):
	_name = "wizard.cpe.line"

	cpe_id = fields.Many2one('wizard.cpe')

	capturar = fields.Boolean()
	item = fields.Integer()
	id_doc = fields.Many2one('account.invoice')
	tipo_doc = fields.Char()
	serie_doc = fields.Char()
	numeracion_doc = fields.Char()
