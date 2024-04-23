# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
from datetime import datetime,timedelta,date
import io
import qrcode
import base64
from monto_a_letras import to_letras
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from suds.client import Client
import ast

from zipfile import ZipFile
import zipfile

import random
import string

import logging
_logger = logging.getLogger(__name__)

import requests

from odoo.tools import float_is_zero, float_compare, pycompat

# mapping invoice type to refund type
TYPE2REFUND = {
	'out_invoice': 'out_refund',        # Customer Invoice
	'in_invoice': 'in_refund',          # Vendor Bill
	'out_refund': 'out_invoice',        # Customer Credit Note
	'in_refund': 'in_invoice',          # Vendor Credit Note
	'out_debito': 'out_debito',
}


class HerenciaFacturaVentas(models.Model):
	_inherit='account.invoice'
	_rec_name='number'

	@api.model
	def _default_tipo_operacion(self):
		model_operacion= self.env['tipo.operacion']
		registro_lineas=model_operacion.search([],order='id asc', limit=1)
		mis_id=0

		for lineas in registro_lineas:
			mis_id = lineas.id
		return mis_id

	def _default_journal_usuario(self):
		if self._context.get('type', 'out_invoice')=="out_refund":
			for line in self.env.user.journal_ids:
				if line.code[0:3]=="NCR":
					return line.id

		elif self._context.get('type', 'out_invoice')=="out_debito":
			for line in self.env.user.journal_ids:
				if line.code[0:3]=="NDB":
					return line.id
		else:
			return self.env.user.journal_id.id



	
	def _dominio_journal(self):
		ids_journal=[]
		if self._context.get('type', 'out_invoice')=="out_refund":
			for line in self.env.user.journal_ids:
				if line.code[0:3]=="NCR":
					ids_journal.append(line.id)
		elif self._context.get('type', 'out_invoice')=="out_debito":
			for line in self.env.user.journal_ids:
				if line.code[0:3]=="NDB":
					ids_journal.append(line.id)
		elif self._context.get('type', 'out_invoice')=="out_invoice":
			for line in self.env.user.journal_ids:
				if line.code[0:3]=="FAC" or line.code[0:3]=="BOL":
					ids_journal.append(line.id)
		return ids_journal



	@api.multi
	def get_taxes_values(self):
		tax_grouped = {}
		for line in self.invoice_line_ids:
			price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
			price_unit2 = price_unit - (price_unit * self.descuentos_globales_mto_prc)

			taxes = line.invoice_line_tax_ids.compute_all(price_unit2, self.currency_id, line.quantity, line.product_id, self.partner_id)['taxes']
			for tax in taxes:
				val = self._prepare_tax_line_vals(line, tax)
				key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)

				if key not in tax_grouped:
					tax_grouped[key] = val
				else:
					tax_grouped[key]['amount'] += val['amount']
					tax_grouped[key]['base'] += val['base']
		return tax_grouped

	
	@api.one
	@api.depends('descuentos_globales_prc','invoice_line_ids.otros_tributos','total_otros_cargos','descuentos_globales_mto',
		'invoice_line_ids.tip_ope_igv', 'invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'tax_line_ids.amount_rounding', 
		'currency_id', 'company_id', 'date_invoice', 'type')
	def _compute_amount(self):
		
		salida = super(HerenciaFacturaVentas, self)._compute_amount()
		
		self.total_bruto = sum(line.quantity * (line.precio_sin_igv * (1 - (line.discount / 100.0))) for line in self.invoice_line_ids)


		if self.total_bruto > 0:
			#pass
			#porcentaje de descuento global
			
			if self.descuentos_globales_prc == True:				
				self.descuentos_globales = sum(line.descuento_global_monto_linea for line in self.invoice_line_ids)
						
			else:
				self.descuentos_globales = self.descuentos_globales_mto
			
		else:
			return
		

		self.descuentos_globales_mto_prc = round(self.descuentos_globales/(sum(line.price_unit * line.quantity for line in self.invoice_line_ids)),15)
		
		
		if self.descuentos_globales_mto_prc:
			for items in self.invoice_line_ids:
				items._compute_price()

			self.descuentos_globales = sum(line.descuento_global_monto_linea for line in self.invoice_line_ids) 
		

		self.total_operaciones_gravadas = sum(line.price_subtotal - (line.price_subtotal * self.descuentos_globales_mto_prc) for line in self.invoice_line_ids if line.nombre_impuesto == 'IGV')		
		self.total_operaciones_exoneradas = sum(line.price_subtotal for line in self.invoice_line_ids if line.nombre_impuesto == 'EXO')
		self.total_operaciones_gratuitas = sum(line.price_subtotal_signed for line in self.invoice_line_ids if line.nombre_impuesto == 'GRA')
		self.total_operaciones_inafectas = sum(line.price_subtotal for line in self.invoice_line_ids if line.nombre_impuesto == 'INA')
		self.total_operaciones_exportadas = sum(line.price_subtotal for line in self.invoice_line_ids if line.nombre_impuesto == 'EXP')

		self.total_otros_tributos = sum(line.otros_tributos for line in self.invoice_line_ids)

		# Cpd. heredado.
		round_curr = self.currency_id.round
		self.amount_untaxed = sum(line.price_subtotal - (line.price_subtotal * self.descuentos_globales_mto_prc) for line in self.invoice_line_ids)

		self.total_final_parcial = (self.amount_untaxed + self.amount_tax) +  self.total_otros_tributos

		self.amount_tax = sum(round_curr(line.amount_total) for line in self.tax_line_ids)
		#self.amount_total = self.amount_untaxed + self.amount_tax   #comentado por ivan
		self.amount_total = self.total_final_parcial + self.total_otros_cargos   # agrege esta linea ivan

		amount_total_company_signed = self.amount_total
		amount_untaxed_signed = self.amount_untaxed
		if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
			currency_id = self.currency_id.with_context(date=self.date_invoice)
			amount_total_company_signed = currency_id.compute(self.amount_total, self.company_id.currency_id)
			amount_untaxed_signed = currency_id.compute(self.amount_untaxed, self.company_id.currency_id)
		sign = self.type in ['in_refund', 'out_refund'] and -1 or 1
		self.amount_total_company_signed = amount_total_company_signed * sign
		self.amount_total_signed = self.amount_total * sign
		self.amount_untaxed_signed = amount_untaxed_signed * sign
		
		



		return salida


		total =0.0
		prc= 0.0
		prc_igv = 0.0
		total_item=0.00

		tot_grav = 0.0
		tot_exo = 0.0
		tot_ina = 0.0
		tot_exp = 0.0
		tot_grat = 0.0

		totbruto_item = 0.0
		totdescuento_item = 0.0
		prc = 0.0
		total_tributos_extra = 0.0

		'''
		for line in self.invoice_line_ids:

			total_tributos_extra += line.otros_tributos

			#if line.tip_ope_igv.codigo[0:2] not in("10","20","30") or line.tip_ope_igv.codigo != "401":
			if line.tip_ope_igv.cod_tip_tributo.nombre == "GRA":
				total_item = 0.0
			else:
				total_item = line.quantity*line.precio_sin_igv

			totbruto_item += total_item

			descuento_item = total_item * line.discount/100
			totdescuento_item += descuento_item

			total_item -= descuento_item

			total += total_item

			if line.tip_ope_igv.cod_tip_tributo.nombre=="IGV" and line.quantity>=0:				
				tot_grav +=total_item
				prc_igv = line.monto_impuesto_precio/100
				#for xtax in line.invoice_line_tax_ids:
					#prc_igv = xtax.amount / 100
					#break
			if line.tip_ope_igv.cod_tip_tributo.nombre=="EXO" and line.quantity>=0:
				tot_exo +=total_item 
			if line.tip_ope_igv.cod_tip_tributo.nombre=="GRA" and line.quantity>=0:
				tot_grat += (line.quantity *line.price_unit)								
			if line.tip_ope_igv.cod_tip_tributo.nombre=="INA" and line.quantity>=0:
				tot_ina +=total_item 
			if line.tip_ope_igv.cod_tip_tributo.nombre=="EXP" and line.quantity>=0:
				tot_exp +=total_item
		'''

		if total > 0:
			#porcentaje de descuento global
			if self.descuentos_globales_prc == True:				
				self.descuentos_globales = sum(line.descuento_global_monto_linea for line in self.invoice_line_ids)    #total * self.descuentos_globales_mto / 100
						
			else:
				self.descuentos_globales = self.descuentos_globales_mto
				
			prc = self.descuentos_globales/total
		prc = 0.0

		if tot_grav >0 :
			self.total_operaciones_gravadas = round(tot_grav - (tot_grav * prc ), 2)
		if 	tot_exo>0:
			self.total_operaciones_exoneradas = round(tot_exo - (tot_exo * prc ), 2)
		if tot_grat>0:
			self.total_operaciones_gratuitas = round(tot_grat - (tot_grat * prc ), 2)
		if tot_ina>0:
			self.total_operaciones_inafectas = round(tot_ina - (tot_ina * prc ), 2)
		if tot_exp>0:
			self.total_operaciones_exportadas = round(tot_exp - (tot_exp * prc ), 2)

		

		self.total_bruto = round(total,2)
		#self.amount_untaxed = self.total_bruto - self.descuentos_globales
		#self.amount_tax  =  round((tot_grav - (tot_grav * prc )) * prc_igv, 2)
		self.total_otros_tributos = total_tributos_extra
		
		
		self.amount_total = self.total_otros_cargos + self.total_final_parcial		

		self.total_bruto_item = totbruto_item
		self.total_descuento_item = totdescuento_item
		self.descuentos_globales_mto_prc =  round(prc,5)


		for line in self.tax_line_ids:
			line.amount = self.amount_tax






		# Código heredado.
		round_curr = self.currency_id.round
		self.amount_untaxed = sum(line.price_subtotal for line in self.invoice_line_ids)

		self.total_final_parcial = (self.amount_untaxed + self.amount_tax) +  self.total_otros_tributos		

		self.amount_tax = sum(round_curr(line.amount_total) for line in self.tax_line_ids)
		self.amount_total = self.amount_untaxed + self.amount_tax

		amount_total_company_signed = self.amount_total
		amount_untaxed_signed = self.amount_untaxed
		if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
			currency_id = self.currency_id.with_context(date=self.date_invoice)
			amount_total_company_signed = currency_id.compute(self.amount_total, self.company_id.currency_id)
			amount_untaxed_signed = currency_id.compute(self.amount_untaxed, self.company_id.currency_id)
		sign = self.type in ['in_refund', 'out_refund'] and -1 or 1
		self.amount_total_company_signed = amount_total_company_signed * sign
		self.amount_total_signed = self.amount_total * sign
		self.amount_untaxed_signed = amount_untaxed_signed * sign
		
		return salida	
	

	journal2_id = fields.Many2one('account.journal', string='Journal', required=True, domain=lambda self: [('id', 'in', self._dominio_journal())],default=_default_journal_usuario)

	
	tipo_doc=fields.Char(compute='_compute_number', store=True)
	serie=fields.Char(compute='_compute_number', store=True)
	numeracion=fields.Char(compute='_compute_number', store=True)

	#agrega campos probando generacion de codigo QR
	txt_filename = fields.Char(copy = False)
	imagen_qr=fields.Binary(copy = False)
	#-----------------------------------------
	#agrega campo monto_letras
	monto_letras = fields.Char(compute='_amount_letras', store=True)
	#-----------------------------------------

	#nuevos campos tipo afectacion del igv y ripo de operacion
	tipo_operacion=fields.Many2one('tipo.operacion', default = _default_tipo_operacion)
	guia = fields.Char()

	state = fields.Selection(selection_add=[('anulado', 'Anulado')])

	comprobante_artificio_rectificativa = fields.Char()
	numeracion_tree=fields.Integer(compute='_compute_number', store=True)

	rectificativa_motivo = fields.Many2one('rectificativa.motivo')
	correlativo_fisico = fields.Char(copy = False)	
	fecha_fisico = fields.Date(copy = False)
	#campos para creado, firmado y respuesta de xml
	estado_invoice_xml = fields.Selection([('borrador','Borrador'),('generado','Generado'),('enviado','Enviado'),('aceptado','Aceptado'),('rechazado','Rechazado'),('baja','Baja')], track_visibility='onchange', string='Estado deL XML', default="borrador",copy = False,
		help=" * El estado 'Borrador' es cuando el documento XML no esta creado.\n"
			" * El estado 'Generado' es cuando el documento XML esta creado y firmado .\n"
			" * El estado 'Enviado' es cuando ya se envio a sunat el documento XML firmado.\n"
			" * El estado 'Aceptado' es cuando ya se envio a sunat el documento XML firmado y nos respondio satisfactoriamente el CDR .\n"
			" * El estado 'Rechazado' es cuando ya se envio a sunat el documento XML firmado y nos Rechazo el proceso .\n"
			" * El estado 'Baja' es cuando sunat ya nos acepto el documento XML firmado y le hemos dado de baja por diferentes motivos .\n")

	estado_factura_xml = fields.Char(readonly=True,copy = False)
	xml_firmado=fields.Binary(copy = False)
	xml_firmado_filename=fields.Char(copy = False)
	xml_cdr=fields.Binary(help="Constancia de Recepción.",copy = False)
	xml_cdr_filename=fields.Char(copy = False)
	#termina campos para creado, firmado y respuesta de xml

	#campos de suma total parcial segun el tipo de impuesto sunat
	total_bruto = fields.Monetary(store=True, readonly=True, compute='_compute_amount', track_visibility='always')
	descuentos_globales = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')
	descuentos_globales_prc =fields.Boolean(help="Marcar si se desea digital un porcentaje", store=True)
	descuentos_globales_mto =fields.Float()
	descuentos_globales_mto_prc =fields.Float()

	total_operaciones_gravadas = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')
	total_operaciones_exoneradas = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')
	total_operaciones_gratuitas = fields.Monetary(store=True, readonly=True, compute='_compute_amount', track_visibility='always')
	total_operaciones_inafectas = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')	
	total_operaciones_exportadas = fields.Monetary(store=True, readonly=True, compute='_compute_amount', track_visibility='always')

	
	total_bruto_item = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')
	total_descuento_item = fields.Monetary(store=True, readonly=True,compute='_compute_amount', track_visibility='always')

	fecha_crea_invoice = fields.Datetime(copy = False)

	total_otros_tributos = fields.Monetary(store=True, readonly=True, compute='_compute_amount', track_visibility='always')
	total_otros_cargos = fields.Monetary()
	total_final_parcial = fields.Monetary(store=True, readonly=True, compute='_compute_amount', track_visibility='always')

	placa_vehiculo = fields.Char()

	sent_correo = fields.Boolean(default=False, copy=False)

	#nuevo codigo para adjuntar archivos al correo
	attachment_ids = fields.Many2many('ir.attachment', 'factura_attachment_rel', 'factura_id','attachment_id')
	#estado_archivo_adjunto = fields.Selection([('no', 'No cargado'),('si', 'Cargado')],default="no")
	#id_carga_reporte=fields.Integer()
	type = fields.Selection(selection_add=[('out_debito','Nota de debito')])
	#campos para la nota de debito
	debito_motivo = fields.Many2one('debito.motivo')	
	#termina campos para la nota de debito

	sent_pag_custodia = fields.Boolean(default=False, copy=False)
	motivo_anulacion = fields.Char(copy = False)
	fecha_enviado_sunat = fields.Datetime(copy = False)
	nota = fields.Text()

	orden_compra = fields.Char(copy = False)
	documento_relacionado_line = fields.One2many('account.invoice.documentorelacionado.line', 'invoice_id', string="Detalle de los documentos externos" )
	guia_line = fields.One2many('account.invoice.guia.line', 'factura_id', string="Detalle de guias" )


	@api.model
	def invoice_line_move_line_get(self):
		res = []
		for line in self.invoice_line_ids:
			if line.quantity==0:
				continue
			tax_ids = []
			for tax in line.invoice_line_tax_ids:
				tax_ids.append((4, tax.id, None))
				for child in tax.children_tax_ids:
					if child.type_tax_use != 'none':
						tax_ids.append((4, child.id, None))
			analytic_tag_ids = [(4, analytic_tag.id, None) for analytic_tag in line.analytic_tag_ids]

			move_line_dict = {
				'invl_id': line.id,
				'type': 'src',
				'name': line.name.split('\n')[0][:64],
				'price_unit': line.price_unit - (line.price_unit * self.descuentos_globales_mto_prc),
				'quantity': line.quantity,
				'price': line.price_subtotal - (line.price_subtotal * self.descuentos_globales_mto_prc),
				'account_id': line.account_id.id,
				'product_id': line.product_id.id,
				'uom_id': line.uom_id.id,
				'account_analytic_id': line.account_analytic_id.id,
				'tax_ids': tax_ids,
				'invoice_id': self.id,
				'analytic_tag_ids': analytic_tag_ids
			}
			res.append(move_line_dict)
		return res

	@api.onchange('nota')
	def cambia_nota(self):
		self.comment = self.nota

	@api.onchange('partner_id')
	def cambia_partner(self):
		self.comment = False
		self.nota = False

	def descargar_cpe(self):
		if not self.company_id.url_webservice_facturacion:
			return

		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			return

		ruta_archivo_cdr="C://prosystem/CDR/"
		nombre_archivo="%s-%s-%s.xml"% (self.company_id.vat,tipo_documento,self.serie + "-" + self.numeracion)
		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)
		cCDR = client.service.DescargarCdr(ruta_archivo_cdr, nombre_archivo, self.company_id.usuario_sunat,self.company_id.password_sunat, self.company_id.partner_id.vat, tipo_documento, self.serie, int(self.numeracion))
			#_logger.info("CDR:" + cXmlFirmado)

		cCDR2=cCDR.replace("'",'"').replace('{"',"{'").replace('": "',"': '").replace('"}',"'}").replace('", "cdr":"',"', 'cdr':'")
		
		diccionario=ast.literal_eval(cCDR2)

		self.estado_factura_xml=diccionario['mensaje']			

		if not  diccionario.get('cdr'):
			return
		
		self.xml_cdr = diccionario['cdr']
		self.xml_cdr_filename = "R-" + nombre_archivo
		self.estado_invoice_xml ="aceptado"

	@api.multi
	@api.onchange('correlativo_fisico')
	def _correlativo_fisico(self):
		if not self.correlativo_fisico:
			self.fecha_fisico = False
			return

	@api.constrains('rectificativa_motivo')
	def _validando_tipo_ncredito(self):
		if self._context.get('type', 'out_invoice') == "out_refund":
			if not self.rectificativa_motivo:
				raise ValidationError(_('Debe eligir un tipo de nota de credito'))

	@api.constrains('debito_motivo')
	def _validando_tipo_ndebito(self):
		if self._context.get('type', 'out_invoice') == "out_debito":
			if not self.debito_motivo:
				raise ValidationError(_('Debe eligir un tipo de nota de debito'))

	@api.constrains('name',)
	def _validando_name_motivo(self):
		if self._context.get('type', 'out_invoice') in ("out_refund","out_debito"):
			if not self.name:
				raise ValidationError(_('Debe ingresar un motivo'))



	@api.constrains('refund_invoice_id','correlativo_fisico')
	def _validando_documento_fisico(self):
		if self._context.get('type', 'out_invoice') in ("out_refund","out_debito"):
			if not self.refund_invoice_id and not self.correlativo_fisico:
				raise ValidationError(_('Debe eligir un documento de origen o ingresar un correlativo de un documento físico'))
			if self.refund_invoice_id and self.correlativo_fisico:
				raise ValidationError(_('Debe eligir un documento de origen o ingresar un correlativo de un documento físico y no ambos'))
			if self.correlativo_fisico:
				if not self.fecha_fisico:
					raise ValidationError(_('Debe eligir la fecha física'))
				fecha = self.fecha_fisico			
				date_fisico = datetime.strptime(fecha, '%Y-%m-%d').date()

				fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			

				fecha_actual_str=str(fecha_actual)

				if date_fisico > fecha_actual:
					raise ValidationError(_('Ingrese una fecha no mayor a  la fecha actual: %s')% (fecha_actual_str[8:]+'/' + fecha_actual_str[5:7]  + '/' + fecha_actual_str[0:4]))
			

	def valida_cpe(self):
		tipodoc = ""
		if self.tipo_doc== 'FAC':
			tipodoc = "03"
		if self.tipo_doc== 'BOL':
			tipodoc = "06"
		if self.tipo_doc== 'NCD' and self.serie[0:1]=='B':
			tipodoc = "11"
		if self.tipo_doc== 'NDB' and self.serie[0:1]=='B':
			tipodoc = "12"
		if self.tipo_doc== 'NCD' and self.serie[0:1]=='F':
			tipodoc = "04"
		if self.tipo_doc== 'NDB' and self.serie[0:1]=='F':
			tipodoc = "05"

		fecha = self.date_invoice[8:]+'/' + self.date_invoice[5:7]  + '/' + self.date_invoice[0:4]
		url = "https://prosystemperu.com/valida_cpe.html?ruc=%s&tipocomprobante=%s&cod_docide=%s&num_docide=%s&num_serie=%s&num_comprob=%s&fec_emision=%s&cantidad=%s" % (self.company_id.partner_id.vat, tipodoc, self.partner_id.tipo_documento, self.partner_id.vat,self.serie, self.numeracion, fecha, str(self.amount_total) )
		return {
			'name'     : 'Ir a website',
			'res_model': 'ir.actions.act_url',
			'type'     : 'ir.actions.act_url',
			'target'   : 'current',
			'url'      : url
		}

	@api.constrains('journal2_id','partner_id')
	def _validando_factura_ruc(self):		
		#for invoice in self:
		if self.journal2_id.code[0:3] == "FAC" and self.partner_id.tipo_documento == "1":
			raise ValidationError(_('Si el comprobante es Factura, el tipo de documento del cliente debe ser RUC'))			


	@api.multi
	def name_get(self):
		TYPES = {
			'out_invoice': _('Invoice'),
			'in_invoice': _('Vendor Bill'),
			'out_refund': _('Credit Note'),
			'out_debito': _('Nota debito'),
			'in_refund': _('Vendor Credit note'),
		}
		result = []
		for inv in self:
			result.append((inv.id, "%s %s" % (inv.number or TYPES[inv.type], inv.name or '')))
		return result
	

	@api.multi
	def envio_automatico_correo(self):

		id_carga_reporte_pdf=self.genera_reporte_pdf()
		#self.estado_archivo_adjunto="no"
		
		
		self.env.cr.execute("""SELECT txt_binary from reporte_crystalreport where id=%s"""% id_carga_reporte_pdf)
		byte_pdf=self.env.cr.fetchall()[0][0]
		#compa.mi_texto=byte_pdf.decode("utf-8")

		tipo_documento=""

		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			return
		nombre_archivo=self.company_id.vat + "-"+ tipo_documento + "-"+ self.serie + "-" + self.numeracion


		reg_attachment = {'name':'%s.pdf'%nombre_archivo,
				'datas_fname':'%s.pdf'%nombre_archivo,
				'res_name':'FA/FACTURA',
				'res_model':'account.invoice',
				'company_id': self.company_id.id,
				'type':'binary',
				'public':False,						
				'datas':byte_pdf
				}

		fact_attachment=self.env['ir.attachment'].create(reg_attachment)

		datito=[]

		datito.append(fact_attachment.id)
		#datito.append(mail2_attachment.id)


		if not self.xml_firmado:
			self.enviar_xml("")

		reg_attachment_xml = {'name':self.xml_firmado_filename,
				'datas_fname':self.xml_firmado_filename,
				'res_name': self.number,
				'res_model':'account.invoice',
				'company_id': self.company_id.id,
				'type':'binary',
				'public':False,						
				'datas':self.xml_firmado
				}

		fact_attachment_xml=self.env['ir.attachment'].create(reg_attachment_xml)
		datito.append(fact_attachment_xml.id)

		reg_archivo_invoice = {'attachment_ids': [(6,0,datito)]}
		self.env['account.invoice'].browse(self.id).write(reg_archivo_invoice)

		reg_archivo = {'attachment_ids': [(6,0,datito)],'report_template': False}
		
		self.ensure_one()
		template = self.env.ref('account.email_template_edi_invoice', False)

		mi_template=self.env['mail.template'].browse(template.id)
		mi_template.write(reg_archivo)

		self.sent_correo = True

		template.send_mail(self.id,force_send=True)		
	

	@api.onchange('amount_total')
	def _onchange_amount_total(self):
		for dato in self:
			res = {}
			if dato.descuentos_globales_prc == True:
				if dato.descuentos_globales_mto > 100:
					dato.descuentos_globales_mto = 0
					#raise Warning(_('Ingrese un porcentaje no mayor a 100.'))
					warning = {'title': "Advertencia!",'message': "Ingrese un porcentaje no mayor a 100"}                                              
					return {'value': res, 'warning': warning }
			else:
				if dato.total_bruto < dato.descuentos_globales_mto:
					dato.descuentos_globales_mto = 0
					warning = {'title': "Advertencia!",'message': "Ingrese un monto de descuento menor al total bruto"}                                              
					return {'value': res, 'warning': warning }


			if dato.amount_total < 0:
				raise Warning(_('No puede validar una factura con un importe total negativo. Debería emitir una rectificativa en su lugar.'))


	@api.constrains('tax_line_ids')
	def _validando_impuestos_linea(self):
		count = 0
		for tax in self.tax_line_ids:
			count += 1

		if count > 1:
			raise ValidationError(_('Usted debe ingresar un solo impuesto por Comprobante'))

		

	@api.constrains('journal2_id')
	def _validando_journal(self):
		for invoice in self:
			tipo_documento = ['FAC','BOL','NCR','NDB']

			journal = invoice.journal2_id.sequence_id.prefix
			#journal_modificado = journal[:len(journal)-1]    #obtiene por ejemplo FAC/F001

			
			posicion_corte=journal.find("/")
			if posicion_corte == -1:				
				raise ValidationError(_('La sequencia del journal no tiene el primer separador "/"'))


			tipo=journal[:posicion_corte]
			

			count=0
			for t_doc in tipo_documento:
				
				if t_doc == tipo:
					count +=1

			if count == 1:
				serie_todo = journal[posicion_corte+1:]
				posicion_corte2=serie_todo.find("-")		


				if posicion_corte2 == -1 :
					raise ValidationError(_('La sequencia del journal no tiene el ultimo separador "-"'))

				serie=serie_todo[:len(serie_todo)-1]
				longitud_serie = len(serie)
				inicial_serie = serie[0:1]

				if tipo=='FAC' and inicial_serie not in ("F",'0'):
					raise ValidationError(_('La sequencia del journal para Facturas debe tener como primer digito la letra "F" en su serie'))

				if tipo=='BOL' and inicial_serie not in ("B",'0'):
					raise ValidationError(_('La sequencia del journal para Boletas debe tener como primer digito la letra "B" en su serie'))

				if (tipo=='NCR' and inicial_serie != "B" and inicial_serie != "F"):
					raise ValidationError(_('La sequencia del journal para Nota de credito debe tener como primer digito la letra "F" o "B" en su serie'))

				if (tipo=='NDB' and inicial_serie != "B" and inicial_serie != "F"):
					raise ValidationError(_('La sequencia del journal para Nota de Debito debe tener como primer digito la letra "F" o "B" en su serie'))


				if longitud_serie != 4 and inicial_serie != '0' :						
					raise ValidationError(_('La sequencia del journal,la serie tiene debe tener 4 digitos de longitud ejm: F001'))

			#else:
			#		raise ValidationError(_('La sequencia del journal no encuentra el tipo de documento bien configurado'))
			




	@api.constrains('date_invoice')
	def _check_cash_rounding(self):
		if not self.date_invoice:
			return
		for data in self:
			fecha = data.date_invoice			
			date_object = datetime.strptime(fecha, '%Y-%m-%d').date()

			fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			
			fecha_actual_str=str(fecha_actual)

			if date_object<fecha_actual-timedelta(days=7):
				raise ValidationError(_('Ingrese una fecha no menor a 7 dias antes de la fecha actual: %s')% (fecha_actual_str[8:]+'/' + fecha_actual_str[5:7]  + '/' + fecha_actual_str[0:4]))

			if date_object>fecha_actual:
				raise ValidationError(_('Ingrese una fecha no mayor a  la fecha actual: %s')% (fecha_actual_str[8:]+'/' + fecha_actual_str[5:7]  + '/' + fecha_actual_str[0:4]))

	@api.multi
	@api.onchange('partner_id','journal2_id')
	def _dominio_factura_ref(self):
		if not self.partner_id:
			return
		if not self.journal2_id:
			return
		
		cadena_prefix = str(self.journal2_id.sequence_id.prefix)
		buscar = cadena_prefix.find("/")
		cadena_buscar = cadena_prefix[buscar+1:len(cadena_prefix)-1]
		self.comprobante_artificio_rectificativa = cadena_buscar
	



	@api.multi
	def accion_anular_factura(self):		
		return{
		'view_mode': 'form',
		#'res_id': mi_id,
		'res_model': 'wizard.anulacion',
		'view_type': 'form',
		'type': 'ir.actions.act_window',
		'target': 'new',
		'flags': {'action_buttons': False},		
		}
	

	@api.onchange('journal2_id')
	def onchange_journal2_id(self):
		if not self.journal2_id:			
			return		
		self.journal_id=self.journal2_id


	@api.depends('number')
	def _compute_number(self):

		for atra in self:

			if atra.number and self._context.get('type', 'out_invoice')[0:3]=="out":				

				x = atra.number
				s=x.find("/")
				mi_tip_doc = x[0:s]

				atra.tipo_doc=mi_tip_doc

				c=x.find("-")
				mi_serie = x[s+1:c]

				mi_numeracion = x[c+1:]

				atra.serie=mi_serie
				atra.numeracion=mi_numeracion
				atra.numeracion_tree=int(atra.numeracion)

	@api.multi
	def generando_json(self):

		xjson = []
		# cabecera
		self.env.cr.execute("""SELECT to_json(data) from(
						select to_char(a.date_invoice, 'YYYY-MM-DD') fechaemision,
						lpad(extract(hour from a.fecha_crea_invoice at time zone 'utc')::text, 2,'0')||':'||
						lpad(extract(minute from a.fecha_crea_invoice at time zone 'utc')::text, 2,'0') ||':'||
						lpad(extract(second from a.fecha_crea_invoice at time zone 'utc')::text, 2,'0') horaemision, 
						case a.tipo_doc when 'FAC' then '01' when 'BOL' then '03' when 'NCR' then '07' when 'NDB' then '08' else 'XX' end::varchar(2) tipodocumento,
						(a.serie||'-'||a.numeracion) iddocumento, to_char(a.date_due,'YYYY-MM-DD') fechavencimiento,
						'0.00'::numeric(10,2) calculodetaccion, COALESCE(a.placa_vehiculo,'') placavehiculo,
						b.name moneda,c.codigo tipooperacion,a.total_operaciones_gravadas gravadas,
						COALESCE(a.total_operaciones_gratuitas, 0.00)::numeric(12,2) gratuitas,
						a.amount_tax totaligv, a.total_operaciones_inafectas inafectas,a.total_operaciones_exoneradas exoneradas,
						a.amount_total totalventa,'0.00'::numeric(12,2) montodetraccion,'0.00'::numeric(12,2) montopercepcion,
						(a.monto_letras||' '||COALESCE(b.descripcion,''))::varchar montoenletras,
						a.descuentos_globales descuentoglobal,COALESCE(a.total_bruto,0.00)::numeric(12,2) descuentoglobalbase, 
						COALESCE(round(a.descuentos_globales_mto_prc::numeric, 5),0.00000)::numeric descuentoglobalprc,
						''::varchar tipodocanticipo,''::varchar docanticipo,'0.00'::numeric(12,2) montoanticipo,''::varchar monedaanticipo,
						(COALESCE(a.total_descuento_item,0.00) + COALESCE(a.descuentos_globales,0.00))::numeric(12,2) descuentototal,
						COALESCE(a.total_bruto_item,0.00) totalbrutoitem,
						COALESCE(a.total_otros_tributos,0.00) totalotrostributos, COALESCE(a.total_otros_cargos, 0.00) totalotroscargos, COALESCE(a.total_final_parcial,0.0) totalparcial,
						COALESCE(a.amount_untaxed,0.00) base_imponible,
						COALESCE(b.descripcion,'')::varchar nom_moneda,COALESCE(b.symbol,'') simbolo_moneda,
						('Puede consultar su comprobante electronico en:'||' '||COALESCE(d.pag_custodia)) pagina_custodia,
						COALESCE(h.name ,'') condicion_pago,
						COALESCE(a.state,'') estado_factura, COALESCE(a.comment,'') observacion_factura, COALESCE(a.guia,'') guia_factura,
						to_char(a.date_invoice, 'DD/MM/YYYY') fec_emi, to_char(a.date_due,'DD/MM/YYY') fec_venc,
						COALESCE(d.igv_facturacion ,0.00)::numeric(8,2) igv_factura, 
						coalesce(rm.codigo||' '||upper(rm.name), '') tipo_ncred, coalesce(a.name, '')::varchar motivo_ncred,
						coalesce(a.orden_compra,'') nroordencompra
						from account_invoice a
						left join res_currency b on b.id=a.currency_id
						left join tipo_operacion c on c.id=a.tipo_operacion	
						left join res_company d on d.id=a.company_id
						left join rectificativa_motivo rm on(a.rectificativa_motivo = rm.id)
						left join account_payment_term h on h.id=a.payment_term_id					
						where a.id =%s) data"""% self.id)

		lcab = self.env.cr.fetchall()[0][0]

		#Emisor o Company
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT COALESCE(c.tipo_documento,'') tipodocumento,COALESCE(c.vat,'') nrodocumento, COALESCE(c.name,'') nombrelegal,COALESCE(c.nombre_comercial,'') nombrecomercial,
							'0000'::varchar coddomfiscal,COALESCE(d.code,'')::varchar(6) ubigeo,
							COALESCE(c.urbanizacion,'')::varchar urbanizacion,COALESCE(f.name,'')::varchar departamento,COALESCE(g.code,'') codpais,
							COALESCE(e.name,'')::varchar provincia, COALESCE(d.name,'')::varchar distrito,
							COALESCE(aj.direccion, c.street,'')::varchar direccion,
							(COALESCE(d.name,'')||'-'||COALESCE(e.name,'') ||'-'|| COALESCE(f.name,'') ||'-'|| upper(COALESCE(g.name,''))) ubicacion_empresa,
							COALESCE(c.phone,'') telefono_empresa,COALESCE(c.email,'') correo_empresa,
							COALESCE(c.mobile,'') celular_empresa
							from account_invoice a
							left join res_company b on b.id=a.company_id
							left join res_partner c on c.id=b.partner_id
							left join account_journal aj on aj.id=a.journal_id
							left join res_distrito d on d.id=aj.distrito_id
							left join res_provincia e on e.id=aj.provincia_id
							left join res_country_state f on f.id=aj.state_id
							left join res_country g on g.id=c.country_id
							where a.id=%s) data"""% self.id)

		lemisor = self.env.cr.fetchall()[0][0]		
		lcab['emisor']= lemisor

		#Receptor o Cliente
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT COALESCE(c.tipo_documento,'') tipodocumento, COALESCE(c.vat,'') nrodocumento, COALESCE(c.name,'') nombrelegal,COALESCE(c.nombre_comercial,'') nombrecomercial,
							'0000'::varchar coddomfiscal, COALESCE(d.code,'')::varchar(6) ubigeo,
							COALESCE(c.urbanizacion,'')::varchar urbanizacion,COALESCE(f.name,'')::varchar departamento, COALESCE(g.code,'') codpais,
							COALESCE(e.name,'')::varchar provincia,COALESCE(d.name,'')::varchar distrito,COALESCE(c.street,'')::varchar direccion,
							(COALESCE(d.name,'')||'-'||COALESCE(e.name,'') ||'-'|| COALESCE(f.name,'') ||'-'|| upper(COALESCE(g.name,''))) ubicacion_empresa
							from account_invoice a							
							left join res_partner c on c.id=a.partner_id
							left join res_distrito d on d.id=c.distrito_id
							left join res_provincia e on e.id=c.provincia_id
							left join res_country_state f on f.id=c.state_id
							left join res_country g on g.id=c.country_id
							where a.id=%s) data"""% self.id)

		lreceptor = self.env.cr.fetchall()[0][0]		
		lcab['receptor']= lreceptor


		#if self.guia_line:
		#doc relacionado guia
		self.env.cr.execute("""SELECT to_json(data) from(
								select coalesce(td.codigo, '')::varchar tipodocumento,
								coalesce(aigl.serie_guia||'-'||aigl.nro_guia , '')::varchar nrodocumento										
								from account_invoice_guia_line aigl
								left join tipo_documento td on (td.id = aigl.tip_doc_id)
								where aigl.factura_id=%s 
								order by aigl.id) data"""% self.id)

			
		relacionado = self.env.cr.fetchall()

		yy = []
		for rela in relacionado:
			yy.append(rela[0])		

		lcab['relacionadosguias']=yy

		#doc relacionado otros
		self.env.cr.execute("""SELECT to_json(data) from(
								select coalesce(dr.codigo, '')::varchar tipodocumento,
								coalesce(aidr.nro_docrel , '')::varchar nrodocumento										
								from account_invoice_documentorelacionado_line aidr
								left join documentos_relacionados dr on (dr.id = aidr.doc_rel_id)
								where aidr.invoice_id=%s
								order by aidr.id) data"""% self.id)

			
		relacionado_o = self.env.cr.fetchall()

		yyy = []
		for rela_o in relacionado_o:
			yyy.append(rela_o[0])		

		lcab['relacionadosotros']=yyy	
		


		if self.tipo_doc == 'NCR':
			# Relacionados.
			self.env.cr.execute("""SELECT to_json(data) from(
								select coalesce(coalesce(tdoc_ref, substring(correlativo_fisico,1,2)), '')::varchar tipodocumento,
										coalesce(coalesce(serie_ref||'-'||num_ref, lpad(replace(substring(correlativo_fisico,4,3),'_',''),3,'0')||'-'||
										lpad(replace(substring(correlativo_fisico,8),'_',''),8,'0')), '')::varchar nrodocumento, 
										coalesce(to_char(coalesce(fec_ref, fecha_fisico), 'DD/MM/YYY'), '')::varchar fecha_ref
								from account_invoice ai
								left join (select id, case tipo_doc 
											when 'FAC' then '01'
											when 'BOL' then '03'
											else 'XX' end
											tdoc_ref, serie serie_ref, numeracion num_ref, date_invoice fec_ref
										from account_invoice) ref
									on (ref.id = ai.refund_invoice_id)
								where ai.id=%s) data"""% self.id)

			
			relacionado_ncr = self.env.cr.fetchall()

			yyyy = []
			for rela_ncr in relacionado_ncr:
				yyyy.append(rela_ncr[0])		

			lcab['relacionadosotros']=yyyy
				
			

		#Detalle
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT row_number() over(partition by a.invoice_id order by a.invoice_id,a.id) id,
							btrim(coalesce(b.barcode,''))::varchar codigosunat, 
							case when COALESCE(b.default_code,'')='' then COALESCE(b.id::varchar,'')::varchar else COALESCE(b.default_code,'') end::varchar codigointerno,
							substring(replace(btrim(a.name),chr(10), ' - '),1,500)::varchar descripcion,a.quantity::numeric(12,2) cantidad, COALESCE(c.codigo_um,'NIU')::varchar(5) unidadmedida,
							round(a.prec_sin_igv::numeric,2)::numeric(18,2) valorunitario,
							COALESCE( case when a.prec_con_igv=0 then a.prec_con_igv else a.prec_con_igv end,0.0)::numeric(12,2) precioreferencial,
							COALESCE(a.codigo_impuesto,'')::varchar codigoimpuesto, COALESCE(a.nombre_impuesto,'')::varchar nombreimpuesto,
							COALESCE(a.name_impuesto,'')::varchar nameimpuesto, substring(COALESCE(d.codigo,''),1,2)::varchar tipoimpuesto,
							COALESCE(a.categ_impuesto,'')::varchar categimpuesto, a.price_subtotal::numeric(12,2) impuestobase,
							COALESCE(prec_tipo,'')::varchar tipoprecio,
							'00'::varchar descuentotipo,COALESCE(a.discount/100,0.00)::numeric(10,2) descuentoprc,
							COALESCE(a.importe_bruto_item,0.00)::numeric(12,2) descuentobase, COALESCE(a.importe_descuento_item,0.00)::numeric(12,2) descuento,							
							COALESCE(a.price_subtotal * (a.monto_impuesto_precio/100.0), 0.00)::numeric(12,2) impuesto, 
							COALESCE(a.monto_impuesto_precio/100.0,0.00)::numeric(12,2) impuestoprc,
							0.00::numeric(12,2) impuestoselectivo,COALESCE(a.otros_tributos,0.00)::numeric(12,2) otroimpuesto, COALESCE(price_subtotal,0.00)::numeric(12,2) valorventaitem,
							0.0::numeric(5,2) impuestoselectivoprc,
							COALESCE(a.price_unit,0.00) punitario, COALESCE(a.price_subtotal,0.00) importe_producto, COALESCE(c.name,'') um_sunat_nombre,
							COALESCE(c.abreviatura,'')::varchar um_sunat_abrev,
							COALESCE(a.discount,0.00)::numeric(12,2) descuento_porcentaje,COALESCE(a.importe_descuento_item,0.00)::numeric(12,2) descuento_monto,
							COALESCE(d.name,'')::varchar tipo_impuesto_nombre, btrim(a.name) descripcion_rpt 
							from account_invoice_line a
							left join product_product b on b.id=a.product_id
							left join um_sunat c on c.id=b.um_sunat
							left join tipo_afectacion_igv d on d.id=a.tip_ope_igv														
							where a.invoice_id=%s 
							order by a.id) data"""% self.id)

		ldet = self.env.cr.fetchall()

		y = []
		for item in ldet:
			y.append(item[0])		

		lcab['items']=y
		xjson.append(lcab)

		return xjson


	@api.multi
	def crear_xml(self,p_client):		

		json = self.generando_json()

		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"

		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())

		
		cXml = p_client.service.CrearXml("C://prosystem/XML_SINFIRMA/", json_nombre, str(zip_base64))
		
		return cXml



	@api.multi
	def firmar_xml(self,p_client):
		data=self.env['res.company'].browse(self.company_id.id)
		cad_pfx = str(data.certificado_pfx)
		cadena_pfx= cad_pfx[2:len(cad_pfx)-1]

		cXml = self.crear_xml(p_client)

		extension2=False
		if not self.placa_vehiculo:
			extension2= False
		else:
			extension2= True

		cXmlFirmado = p_client.service.FirmarXml(cXml, cadena_pfx, self.company_id.password_certificado,extension2)

		return cXmlFirmado

	@api.multi
	def enviar_xml(self,dato , modo_envio="validar"):

		if not self.company_id.url_webservice_facturacion:
			return

		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			return

		ruta_archivo_xml="C://prosystem/XML/"
		nombre_archivo="%s-%s-%s"% (self.company_id.vat,tipo_documento,self.serie + "-" + self.numeracion)

		
		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)

		if tipo_documento in ('01','03'):

			cXmlFirmado = self.firmar_xml(client)
				#self.envio_automatico_correo()
		elif tipo_documento == '07':
			cXmlFirmado = self.firmar_xml_notacredito(client)			

		else:
			#nota debito
			cXmlFirmado = self.firmar_xml_notadebito(client)

		#enviar
		self.xml_firmado = cXmlFirmado
		self.xml_firmado_filename = nombre_archivo + ".xml"
		
		if self.estado_invoice_xml == "aceptado" or self.estado_invoice_xml == "baja" or self.estado_invoice_xml == "rechazado":
			return
		
		self.estado_invoice_xml = "generado"
	

		if self.serie[0:1] !='B' and modo_envio=='validar':

			cCDR = client.service.EnviarXml(cXmlFirmado,ruta_archivo_xml,nombre_archivo,self.company_id.usuario_sunat,self.company_id.password_sunat,self.company_id.tipo_facturacion)
			#_logger.info("CDR:" + cXmlFirmado)

			cCDR2=cCDR.replace("'",'"').replace('{"',"{'").replace('": "',"': '").replace('"}',"'}").replace('", "cdr":"',"', 'cdr':'")
			
			diccionario=ast.literal_eval(cCDR2)

			self.estado_factura_xml=diccionario['mensaje']
			
				

			if not  diccionario.get('cdr'):
				return
			
			self.xml_cdr = diccionario['cdr']
			self.xml_cdr_filename = "R-" + nombre_archivo + ".xml"
			self.estado_invoice_xml ="aceptado"
			self.fecha_enviado_sunat = fields.Datetime.now()

	
	#agrega funcion genera_codigo_QR para probar generacion de codigo QR y lo llama
	#dentro de la funcion action_invoice_open que pertenece al modelo account.invoice al cual estamos ampliando.
	@api.multi
	def action_invoice_open(self):
		
		self.fecha_crea_invoice = fields.Datetime.now()

		if self.origin and self.type == 'out_invoice':
			for item in self.invoice_line_ids:
				item._compute_price()

			self.compute_taxes()
			self._compute_amount()
			self._compute_residual()

		mivariable=super(HerenciaFacturaVentas, self).action_invoice_open()

		self.genera_codigo_QR()

		if self.origin and self.type == 'out_invoice':
			if self.company_id.imprimir_comprobante == True:
				self.genera_reporte_pdf()
		else:
			self.enviar_xml("", self.company_id.modo_envio_documento)
		
		return mivariable
		

	def genera_codigo_QR(self):
		
		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			return


		frase = str(self.company_id.vat) + "|" + tipo_documento + "|" + str(self.serie) + "|" +str(self.numeracion) + "|" + str(self.amount_tax) + "|" + str(self.amount_total) + "|" + str(self.date_invoice) + "|" + str(self.partner_id.tipo_documento) + "|" + str(self.partner_id.vat) + "|"
		img = qrcode.make(frase)
		'''f = open("output.png", "wb")
		img.save(f)
		f.close()'''

		buf=io.BytesIO()
		img.save(buf)

		out=base64.b64encode(buf.getvalue())				
		buf.close()

		#print (out)


		self.write({'imagen_qr':out,'txt_filename':'qr.png'})
		


	#----------------------------------------------------------
	#funcion _amount_letras para convertir monto a letras el cual llama otra funcion to_letras(esta funcion to_letras debe colocarse en site-packages) 
	@api.depends('amount_total')
	def _amount_letras(self):
		#if self.amount_total<0:
			#return
		for manda in self:
			if manda.amount_total<0:
				return
			letras=to_letras(manda.amount_total)
			manda.monto_letras=letras
	#----------------------------------------------------------

	@api.multi
	@api.constrains('tipo_operacion')
	def validar_tipo_operacion(self):
		if self.tipo_operacion.codigo=="02":
			nerror=0
			for item in self.invoice_line_ids:
				if item.tip_ope_igv.codigo != "40":
					nerror+=1

			if nerror>0:
				raise ValidationError(_('Existen %s registros que no coiciden con el tipo de operación seleccionado')% nerror)


	def invoice_print(self):
		
		mi_id = self.genera_reporte_pdf()

		self.sent = True 

		return{
		'view_mode': 'form',
		'res_id': mi_id,
		'res_model': 'reporte.crystalreport',
		'view_type': 'form',
		'type': 'ir.actions.act_window',
		'target': 'new',
		'flags': {'action_buttons': False},
		}

	@api.multi
	def invoice_print_anulada(self):
		return self.invoice_print()


	#para generar archivo con el webservice para adjuntar a account.invoice
	@api.multi
	def genera_reporte_pdf(self):

		name_modulo=str(self._name)
		nombre_modelo=name_modulo.replace(".","_")		

		data2 =self.env['account.invoice'].browse(self.id)
		cad_qr = str(data2.imagen_qr)
		qr_cadena= cad_qr[2:len(cad_qr)-1]				

		data=self.env['res.company'].browse(self.company_id.id)
		cad_logo = str(data.logo_ultimo)
		cadena_logo= cad_logo[2:len(cad_logo)-1]

		json=self.generando_json()

		json[0]['qr_code']= qr_cadena
		json[0]['logo_code']= cadena_logo

		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"


		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())



		#para llamar al servicio web lo que esta comentado abajo dos lineas
		#_logger.info("QRPDF antes "+ str(json))
		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice)
		respuesta = client.service.odooreporte(self.env.cr.dbname, json_nombre, str(zip_base64))

		
		diccionario = ast.literal_eval(respuesta)  
		nombre_factura=diccionario['nombre']      
		pdf_factura=diccionario['pdf']		

		pdf_registro = {'nombre_modelo': nombre_modelo,
						'id_registro_modelo': self.id,
						'txt_filename': nombre_factura,
						'txt_binary': pdf_factura
						}


		id_reporte=self.env['reporte.crystalreport'].create(pdf_registro)
		return id_reporte.id


	'''@api.multi
	def action_invoice_sent(self):	

		

		name_modulo=str(self._name)
		nombre_modelo=name_modulo.replace(".","_")

		#arch_id=self.env['reporte.crystalreport'].browse(id_reporte)		
		#byte_pdf=arch_id.txt_binary

		self.env.cr.execute("""SELECT txt_binary from reporte_crystalreport where id=%s"""% self.id_carga_reporte)
		byte_pdf=self.env.cr.fetchall()[0][0]
		#compa.mi_texto=byte_pdf.decode("utf-8")

		tipo_documento=""

		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			return
		nombre_archivo=self.company_id.vat + "-"+ tipo_documento + "-"+ self.serie + "-" + self.numeracion


		reg_attachment_pdf = {'name':'%s.pdf'%nombre_archivo,
				'datas_fname':'%s.pdf'%nombre_archivo,
				'res_name':'FA/FACTURA',
				'res_model':'account.invoice',
				'company_id':'1',
				'type':'binary',
				'public':False,						
				'datas':byte_pdf
				}

		fact_attachment_pdf=self.env['ir.attachment'].create(reg_attachment_pdf)

		datito=[]
		if self.xml_firmado:
			reg_attachment_xml = {'name':self.xml_firmado_filename,
					'datas_fname':self.xml_firmado_filename,
					'res_name': self.number,
					'res_model':'account.invoice',
					'company_id':'1',
					'type':'binary',
					'public':False,						
					'datas':self.xml_firmado
					}

			fact_attachment_xml=self.env['ir.attachment'].create(reg_attachment_xml)
			datito.append(fact_attachment_xml.id)

		

		datito.append(fact_attachment_pdf.id)
		

		reg_archivo = {'attachment_ids': [(6,0,datito)]}
		mail_compose=self.env['account.invoice'].browse(self.id).write(reg_archivo)

		#self.estado_archivo_adjunto="no"

		return super(HerenciaFacturaVentas, self).action_invoice_sent()'''


	#termina generar archivo con el web servicepara adjuntar a account.invoice

	#para reescribir la funcion que coloca por defecto el comprobante al hacer rectificativa al cliente

	@api.model
	def _prepare_refund(self, invoice, date_invoice=None, date=None, description=None, journal_id=None, tipo_nota_credito=None):
		
		values = {}
		for field in self._get_refund_copy_fields():
			if invoice._fields[field].type == 'many2one':
				values[field] = invoice[field].id
			else:
				values[field] = invoice[field] or False

		values['invoice_line_ids'] = self._refund_cleanup_lines(invoice.invoice_line_ids)

		tax_lines = invoice.tax_line_ids
		values['tax_line_ids'] = self._refund_cleanup_lines(tax_lines)

		if journal_id:
			journal_comprobante = self.env['account.journal'].browse(journal_id)
			prefijo_comprobante = journal_comprobante.sequence_id.prefix
			prefijo_ncredito = prefijo_comprobante.replace(prefijo_comprobante[0:3],"NCR")

			registro_ncredito = self.env['ir.sequence'].search([('prefix', '=', prefijo_ncredito)])
			journal = self.env['account.journal'].search([('sequence_id', '=', registro_ncredito.id)])			

			#journal = self.env['account.journal'].browse(journal_id)
		elif invoice['type'] == 'in_invoice':
			journal = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
		else:
			journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
		values['journal_id'] = journal.id
		values['journal2_id'] = journal.id
		values['rectificativa_motivo']= tipo_nota_credito

		values['type'] = TYPE2REFUND[invoice['type']]
		values['date_invoice'] = date_invoice or fields.Date.context_today(invoice)
		values['state'] = 'draft'
		values['number'] = False
		values['origin'] = invoice.number
		values['payment_term_id'] = False
		values['refund_invoice_id'] = invoice.id

		if date:
			values['date'] = date
		if description:
			values['name'] = description
		return values

	#termina para reescribir la funcion que coloca por defecto el comprobante al hacer rectificativa al cliente

	# se complementa con la funcion anterior modificada si se agrega el campo rectificativa_motivo
	@api.multi
	@api.returns('self')
	def refund(self, date_invoice=None, date=None, description=None, journal_id=None, tipo_nota_credito=None):
		new_invoices = self.browse()
		for invoice in self:
			# create the new invoice
			values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date, description=description, journal_id=journal_id, tipo_nota_credito=tipo_nota_credito)
			refund_invoice = self.create(values)
			invoice_type = {'out_invoice': ('customer invoices credit note'),'in_invoice': ('vendor bill credit note')}
			message = _("This %s has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a>") % (invoice_type[invoice.type], invoice.id, invoice.number)
			refund_invoice.message_post(body=message)
			new_invoices += refund_invoice
		return new_invoices

	#termina se complementa con la funcion anterior modificada si se agrega el campo rectificativa_motivo


	# Cargar PDF y XML a la pagina de custodia
	def cargar_pdfxml_custodia(self):

		reporte_pdf =  self.env['reporte.crystalreport'].search([('nombre_modelo','=','account_invoice'),('id_registro_modelo','=',self.id)],order="id desc", limit=1)
		if not reporte_pdf:		
			id_reporte=self.genera_reporte_pdf()
			reporte_pdf = self.env['reporte.crystalreport'].browse(id_reporte)

		cad_pdf = str(reporte_pdf.txt_binary)
		pdf = cad_pdf[2:len(cad_pdf)-1]    	
		nombre = reporte_pdf.txt_filename
		tipo = "pdf"
		ws=self.company_id.pag_custodia.replace('http://','').replace('https://','')

		try:
			client = Client(url='https://%s/ws/vfpswscpe.php?wsdl'% ws)
			cRpta1 = client.service.VFPs_UploadFile(tipo,nombre,pdf)
		except Exception as e:
			raise ValidationError("Error publicando el CPE [pdf]")	


		oinvoice = self.env['account.invoice'].browse(self.id)

		if not oinvoice.xml_firmado:
			oinvoice.enviar_xml("")
		
		cad_xml = str(oinvoice.xml_firmado)
		xml = cad_xml[2:len(cad_xml)-1]		
		nombre_xml = oinvoice.xml_firmado_filename
		tipo_xml = "xml"

		try:
			cRpta2 = client.service.VFPs_UploadFile(tipo_xml,nombre_xml,xml)
		except Exception as e:
			raise ValidationError("Error publicando el CPE [xml]")
		
		self.sent_pag_custodia = True

		if self.tipo_doc=='BOL':
			tipo_documento="03"
		elif self.tipo_doc=='FAC':
			tipo_documento="01"
		elif self.tipo_doc=='NCR':
			tipo_documento="07"
		elif self.tipo_doc=='NDB':
			tipo_documento="08"
		else:
			tipo_documento='XX'

		ruc_cliente = self.partner_id.vat
		nombre_cliente = self.partner_id.name
		correo_cliente = self.partner_id.email
		fecha_cpe = self.date_invoice
		total_cpe = str(self.amount_total)
		tipo_doc_cpe = self.tipo_doc
		nombre_documento =self.xml_firmado_filename[:-4]
		serie_cpe = self.serie
		num_cpe = self.numeracion
		bd_cpe = self.company_id.bd_custodia

		sql = """INSERT into usuario(ruc, nombre, email, pass, role, activo) values('%s','%s','%s','%s','user', 1)"""% (ruc_cliente, nombre_cliente, correo_cliente, ruc_cliente) 

		try:
			cRpta2 = client.service.VFPs_SQLExec(sql,bd_cpe)
		except Exception as e:
			raise ValidationError("Error publicando el CPE [usuario]")
		
		
		sql = """ INSERT into documento(unico, cod, ruc, fecha, estab, ptoemi, total, secuencial, claveac, numaut, enviado) 
				values('%s','%s','%s','%s','%s','%s', %s,'%s','%s','', 1)"""% (nombre_documento,tipo_documento, ruc_cliente, fecha_cpe, tipo_documento, serie_cpe, total_cpe, num_cpe, nombre_documento)

		try:
			cRpta2 = client.service.VFPs_SQLExec(sql,bd_cpe)
		except Exception as e:
			raise ValidationError("Error publicando el CPE [documento]")


	def generando_json_ncredito(self):
		self.env.cr.execute("""SELECT to_json(data) from(
							select rm.codigo tipo, serie||'-'||numeracion nroreferencia, ai.name descripcion
							from account_invoice ai
							left join rectificativa_motivo rm on (rm.id = ai.rectificativa_motivo)
							where ai.id=%s) data"""% self.id)

		discr = self.env.cr.fetchall()
		discrepancia = []
		for item in discr:
			discrepancia.append(item[0])

		self.env.cr.execute("""SELECT to_json(data) from(
							select coalesce(tdoc_ref, substring(correlativo_fisico,1,2))::varchar tipodocumento,
									coalesce(serie_ref||'-'||num_ref, lpad(replace(substring(correlativo_fisico,4,3),'_',''),3,'0')||'-'||
									lpad(replace(substring(correlativo_fisico,8),'_',''),8,'0'))::varchar nrodocumento
							from account_invoice ai
							left join (select id, case tipo_doc 
										when 'FAC' then '01'
										when 'BOL' then '03'
										else 'XX' end
										tdoc_ref, serie serie_ref, numeracion num_ref, date_invoice fec_ref
									from account_invoice) ref
								on (ref.id = ai.refund_invoice_id)
							where ai.id=%s) data"""% self.id)

		
		rela = self.env.cr.fetchall()
		relacionado = []
		for item in rela:
			relacionado.append(item[0])

		json = self.generando_json()

		json[0]['discrepancias'] = discrepancia
		json[0]['relacionados'] = relacionado
		_logger.info(str(json))
		return json

	def generando_json_ndebito(self):
		self.env.cr.execute("""SELECT to_json(data) from(
							select dm.codigo tipo, serie||'-'||numeracion nroreferencia, coalesce(ai.name,'')::varchar descripcion
							from account_invoice ai
							left join debito_motivo dm on (dm.id = ai.debito_motivo)
							where ai.id=%s) data"""% self.id)

		discr = self.env.cr.fetchall()
		discrepancia = []
		for item in discr:
			discrepancia.append(item[0])

		self.env.cr.execute("""SELECT to_json(data) from(
							select coalesce(tdoc_ref, substring(correlativo_fisico,1,2))::varchar tipodocumento,
									coalesce(serie_ref||'-'||num_ref, lpad(replace(substring(correlativo_fisico,4,3),'_',''),3,'0')||'-'||
									lpad(replace(substring(correlativo_fisico,8),'_',''),8,'0'))::varchar nrodocumento
							from account_invoice ai
							left join (select id, case tipo_doc 
										when 'FAC' then '01'
										when 'BOL' then '03'
										else 'XX' end
										tdoc_ref, serie serie_ref, numeracion num_ref, date_invoice fec_ref
									from account_invoice) ref
								on (ref.id = ai.refund_invoice_id)
							where ai.id=%s) data"""% self.id)

		
		rela = self.env.cr.fetchall()
		relacionado = []
		for item in rela:
			relacionado.append(item[0])

		json = self.generando_json()

		json[0]['discrepancias'] = discrepancia
		json[0]['relacionados'] = relacionado
		_logger.info(str(json))
		return json

	@api.multi
	def crear_xml_notacredito(self,p_client):
		json = self.generando_json_ncredito()

		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"

		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())

		
		cXml = p_client.service.CrearXmlNotaCredito("C://prosystem/XML_SINFIRMA/", json_nombre, str(zip_base64))
		_logger.info("XML:" + cXml )
		return cXml

	@api.multi
	def firmar_xml_notacredito(self,p_client):
		data=self.env['res.company'].browse(self.company_id.id)
		cad_pfx = str(data.certificado_pfx)
		cadena_pfx= cad_pfx[2:len(cad_pfx)-1]

		cXml = self.crear_xml_notacredito(p_client)

		extension2=False
		if not self.placa_vehiculo:
			extension2= False
		else:
			extension2= True

		cXmlFirmado = p_client.service.FirmarXmlNotaCredito(cXml, cadena_pfx, self.company_id.password_certificado,extension2)

		return cXmlFirmado

	@api.multi
	def crear_xml_notadebito(self,p_client):
		json = self.generando_json_ndebito()

		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"

		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())

		
		cXml = p_client.service.CrearXmlNotaDebito("C://prosystem/XML_SINFIRMA/", json_nombre, str(zip_base64))
		_logger.info("XML:" + cXml )
		return cXml

	@api.multi
	def firmar_xml_notadebito(self,p_client):
		data=self.env['res.company'].browse(self.company_id.id)
		cad_pfx = str(data.certificado_pfx)
		cadena_pfx= cad_pfx[2:len(cad_pfx)-1]

		cXml = self.crear_xml_notadebito(p_client)

		extension2=False
		if not self.placa_vehiculo:
			extension2= False
		else:
			extension2= True

		cXmlFirmado = p_client.service.FirmarXmlNotaDebito(cXml, cadena_pfx, self.company_id.password_certificado,extension2)

		return cXmlFirmado
	

	
class MailComposer(models.TransientModel):
	_inherit = 'mail.compose.message'

	@api.multi
	def onchange_template_id(self,template_id,composition_mode,model,res_id):

		r = super(MailComposer, self).onchange_template_id(template_id,composition_mode,model,res_id)

		context = dict(self._context or {})
		if context.get('active_model') == 'account.invoice':		 		
			ai_id = self._context['active_ids'][0]
			ids = []
			for line in self.env['account.invoice'].search([('id', '=', ai_id)]):
				for lines_attachment in line.attachment_ids:
					ids.append(lines_attachment.id)

			mi_res={'attachment_ids':ids}
			r['value'].update(mi_res)

		'''if r['value']['attachment_ids']:
			ids.insert(0, r['value']['attachment_ids'][0])
			r['value']['attachment_ids'] = ids'''
		return r

#termina nuevo codigo para adjuntar archivos al correo

	


class HerenciaFacturaVentasLine(models.Model):
	_inherit='account.invoice.line'

	@api.model
	def _default_tip_ope_igv(self):
		model_tipo_igv = self.env['tipo.afectacion.igv']
		registro_lineas = model_tipo_igv.search([],order='id asc', limit=1)
		mi_id=0

		for linea in registro_lineas:
			mi_id = linea.id
		return mi_id

	#nuevos campos tipo afectacion del igv y ripo de operacion
	tip_ope_igv=fields.Many2one('tipo.afectacion.igv', default = _default_tip_ope_igv)
	#umedida_sunat = fields.Char(related="product_id.um_sunat.name")
	umedida_sunat = fields.Char(compute='onchange_umedida_sunat',store=True)

	primer_digito_tip_ope_igv =  fields.Char(compute='validando_tip_afe_igv',store=True)

	condicion_impuesto_precio = fields.Boolean()
	monto_impuesto_precio = fields.Float()

	precio_sin_igv = fields.Float()
	otros_tributos = fields.Float()

	prec_sin_igv = fields.Float()
	prec_con_igv = fields.Float()
	prec_tipo = fields.Char()

	prec_con_igv_ref = fields.Float()
	importe_bruto_item = fields.Float()
	importe_descuento_item = fields.Float()

	codigo_impuesto = fields.Char()
	nombre_impuesto = fields.Char()
	name_impuesto = fields.Char()
	categ_impuesto = fields.Char()

	descuento_global_monto_linea = fields.Float()
	importe_base_line = fields.Float()
	igv_monto_linea = fields.Float()


	@api.constrains('price_unit')
	def _validando_precio(self):	
		for linea in self:
			if linea.price_unit == 0 or not linea.price_unit:
				raise ValidationError(_('El precio del producto debe ser mayor a cero'))



	#@api.depends('price_unit','invoice_line_tax_ids','tip_ope_igv','quantity')	
	def calculo_precio_sin(self,price):
		
		if not price:
			return

		if self.condicion_impuesto_precio == True:
			self.precio_sin_igv = price / (1 + (self.monto_impuesto_precio / 100))
		else:
			self.precio_sin_igv = price

		tafe = self.tip_ope_igv.codigo

		self.importe_bruto_item = round(self.quantity * self.precio_sin_igv, 2)
		self.importe_descuento_item = round(self.quantity * self.precio_sin_igv * (self.discount / 100), 2)


		if self.tip_ope_igv and tafe[0:1]=="1":
			if self.invoice_line_tax_ids.price_include==True:
				prec_igv = price
			else:
				prec_igv = price + round(price*self.monto_impuesto_precio/100, 2)
		else:
			prec_igv = price
		

		if self.tip_ope_igv.cod_tip_tributo.nombre != "GRA":
			self.prec_con_igv_ref =0.0
			self.prec_con_igv = prec_igv			
			self.prec_sin_igv = round(self.precio_sin_igv,2)
			self.prec_tipo = "01"
		else:
			self.prec_con_igv_ref = round(self.precio_sin_igv,2)
			self.prec_tipo = "02"
			self.prec_con_igv = 0.0
			self.prec_sin_igv = 0.0

		self.codigo_impuesto= self.tip_ope_igv.cod_tip_tributo.codigo
		self.nombre_impuesto=  self.tip_ope_igv.cod_tip_tributo.nombre
		self.name_impuesto =  self.tip_ope_igv.cod_tip_tributo.codigo_internacional
		self.categ_impuesto = self.tip_ope_igv.cod_tip_tributo.categoria

		'''
		for data1 in self:
			data1._onchange_impuesto_igv()

		_logger.info("DEPENDS: CALCULO PRECIO IGV")
		for data in self:
			if not data.price_unit:
				return
			if data.condicion_impuesto_precio==True:
				data.precio_sin_igv = data.price_unit/(1 + (data.monto_impuesto_precio/100))
				# Prueba - GABRIEL
				#data.price_subtotal = data.precio_sin_igv
			else:
				data.precio_sin_igv = data.price_unit


			tafe = data.tip_ope_igv.codigo

			data.importe_bruto_item = round(data.quantity* data.precio_sin_igv, 2)
			data.importe_descuento_item= round(data.quantity * data.precio_sin_igv * (data.discount/100),2)


			if data.tip_ope_igv and tafe[0:1]=="1":
				if data.invoice_line_tax_ids.price_include==True:
					prec_igv = data.price_unit
				else:
					prec_igv = data.price_unit + round(data.price_unit*data.monto_impuesto_precio/100, 2)
			else:
				prec_igv = data.price_unit
			

			if data.tip_ope_igv.cod_tip_tributo.nombre != "GRA":
				data.prec_con_igv_ref =0.0
				data.prec_con_igv = prec_igv			
				data.prec_sin_igv = round(data.precio_sin_igv,2)
				data.prec_tipo = "01"
			else:
				data.prec_con_igv_ref = round(data.precio_sin_igv,2)
				data.prec_tipo = "02"
				data.prec_con_igv = 0.0
				data.prec_sin_igv = 0.0

			data.codigo_impuesto= data.tip_ope_igv.cod_tip_tributo.codigo
			data.nombre_impuesto=  data.tip_ope_igv.cod_tip_tributo.nombre
			data.name_impuesto =  data.tip_ope_igv.cod_tip_tributo.codigo_internacional
			data.categ_impuesto = data.tip_ope_igv.cod_tip_tributo.categoria
		'''


	#@api.onchange('invoice_line_tax_ids')
	def _onchange_impuesto_igv(self):
		#modifique ultimo esta linea 8/11/2018  ivan
		'''if not self.invoice_line_tax_ids:
			self.condicion_impuesto_precio = False
			self.monto_impuesto_precio = 0.00

		for impuesto in self.invoice_line_tax_ids:
			if impuesto:
				self.condicion_impuesto_precio = impuesto.price_include
				self.monto_impuesto_precio = impuesto.amount'''
		#termina modifique ultimo esta linea 8/11/2018  ivan
		
		if self.invoice_line_tax_ids:
			self.condicion_impuesto_precio = self.invoice_line_tax_ids.price_include
			self.monto_impuesto_precio = self.invoice_line_tax_ids.amount
		else:
			self.condicion_impuesto_precio = False
			self.monto_impuesto_precio = 0.0
		

	@api.depends('product_id')
	def onchange_umedida_sunat(self):
		for line in self:
			line.umedida_sunat=line.product_id.um_sunat.name

	
	@api.one
	@api.depends('tip_ope_igv')	
	def validando_tip_afe_igv(self):

		if self.tip_ope_igv:
			self.primer_digito_tip_ope_igv = self.tip_ope_igv.codigo
			if self.primer_digito_tip_ope_igv not in("10", "171"):
				self.invoice_line_tax_ids = False
		else:
			self.invoice_line_tax_ids = False

		
	
	@api.one
	@api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
	'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
	'invoice_id.date_invoice', 'invoice_id.date', 'tip_ope_igv','invoice_id.descuentos_globales_mto')
	def _compute_price(self):

		currency = self.invoice_id and self.invoice_id.currency_id or None
		price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
		price_dscto = 0.0

		# Para calcular el precio sin IGV
		price_base = self.price_unit

		price2 = price

		if self.invoice_id.descuentos_globales_mto:
			price_dscto = price
			price2 = price - (price * self.invoice_id.descuentos_globales_mto_prc)
		

		taxes = False
		if self.invoice_line_tax_ids:
			taxes = self.invoice_line_tax_ids.compute_all(price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id)
		
		self.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else self.quantity * price

		#if self.condicion_impuesto_precio == True:
		tot_excluido = self.price_subtotal
		#else:
		#	tot_excluido = taxes['total_included'] if taxes else self.quantity * price
		
		if self.invoice_line_tax_ids:
			taxes = self.invoice_line_tax_ids.compute_all(price2, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id)

		self.price_total = taxes['total_included'] if taxes else self.price_subtotal

		#if self.condicion_impuesto_precio == True:
		self.descuento_global_monto_linea = tot_excluido - taxes['total_excluded'] if taxes else self.price_subtotal - tot_excluido
		#else:
		#	self.descuento_global_monto_linea = tot_excluido - taxes['total_included'] if taxes else self.price_subtotal - tot_excluido

		if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
			price_subtotal_signed = self.invoice_id.currency_id.with_context(date=self.invoice_id._get_currency_rate_date()).compute(price_subtotal_signed, self.invoice_id.company_id.currency_id)
		sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
		self.price_subtotal_signed = price_subtotal_signed * sign
		

		
		#salida = super(HerenciaFacturaVentasLine, self)._compute_price()
		
		if self.tip_ope_igv.cod_tip_tributo.nombre == "GRA":
			self.price_subtotal = 0.00
			self.price_total = 0.00 
		
		
		self._onchange_impuesto_igv()

		self.calculo_precio_sin(price_base)

		"""
		if self.condicion_impuesto_precio:
			price_dscto = (price_dscto / (1 + (self.monto_impuesto_precio / 100.0))) 

		price_dscto = price_dscto * (self.invoice_id.descuentos_globales_mto_prc)

		self.descuento_global_monto_linea = self.quantity*price_dscto
		"""

		'''if self.tip_ope_igv.cod_tip_tributo.nombre == "IGV":
			self.descuento_global_monto_linea = self.price_subtotal * self.invoice_id.descuentos_globales_mto/100
			self.importe_base_line =  self.price_subtotal - self.descuento_global_monto_linea
			self.igv_monto_linea = self.importe_base_line * self.monto_impuesto_precio/100

		else:
			precio_subtotal = self.quantity * self.precio_sin_igv
			self.descuento_global_monto_linea = precio_subtotal * self.invoice_id.descuentos_globales_mto/100
			self.importe_base_line =  precio_subtotal - self.descuento_global_monto_linea
			self.igv_monto_linea = self.importe_base_line * self.monto_impuesto_precio/100'''

		#return salida

	@api.multi
	@api.constrains('invoice_line_tax__ids','tip_ope_igv') 
	def _validando_tipo_impuesto_igv(self):
		for line in self:
			if (line.tip_ope_igv.codigo== "10" and not line.invoice_line_tax_ids) or (line.tip_ope_igv.codigo== "171" and not line.invoice_line_tax_ids):
				raise ValidationError(_('La operación gravada debe tener IGV'))

	def _set_taxes(self):
		""" Used in on_change to set taxes and price."""
		if self.invoice_id.type in ('out_invoice', 'out_refund', 'out_debito'):
			taxes = self.product_id.taxes_id or self.account_id.tax_ids
		else:
			taxes = self.product_id.supplier_taxes_id or self.account_id.tax_ids

		# Keep only taxes of the company
		company_id = self.company_id or self.env.user.company_id
		taxes = taxes.filtered(lambda r: r.company_id == company_id)

		self.invoice_line_tax_ids = fp_taxes = self.invoice_id.fiscal_position_id.map_tax(taxes, self.product_id, self.invoice_id.partner_id)

		fix_price = self.env['account.tax']._fix_tax_included_price
		if self.invoice_id.type in ('in_invoice', 'in_refund'):
			prec = self.env['decimal.precision'].precision_get('Product Price')
			if not self.price_unit or float_compare(self.price_unit, self.product_id.standard_price, precision_digits=prec) == 0:
				self.price_unit = fix_price(self.product_id.standard_price, taxes, fp_taxes)
		else:
			self.price_unit = fix_price(self.product_id.lst_price, taxes, fp_taxes)

	@api.onchange('product_id')
	def _onchange_product_id(self):
		domain = {}
		if not self.invoice_id:
			return

		part = self.invoice_id.partner_id
		fpos = self.invoice_id.fiscal_position_id
		company = self.invoice_id.company_id
		currency = self.invoice_id.currency_id
		type = self.invoice_id.type

		if not part:
			warning = {
					'title': _('Warning!'),
					'message': _('You must first select a partner!'),
				}
			return {'warning': warning}

		if not self.product_id:
			if type not in ('in_invoice', 'in_refund'):
				self.price_unit = 0.0
			domain['uom_id'] = []
		else:
			if part.lang:
				product = self.product_id.with_context(lang=part.lang)
			else:
				product = self.product_id

			self.name = product.partner_ref
			account = self.get_invoice_line_account(type, product, fpos, company)
			if account:
				self.account_id = account.id
			self._set_taxes()

			if type in ('in_invoice', 'in_refund'):
				if product.description_purchase:
					self.name += '\n' + product.description_purchase
			else:
				if product.description_sale:
					self.name = self.name

			if not self.uom_id or product.uom_id.category_id.id != self.uom_id.category_id.id:
				self.uom_id = product.uom_id.id
			domain['uom_id'] = [('category_id', '=', product.uom_id.category_id.id)]

			if company and currency:
				if company.currency_id != currency:
					self.price_unit = self.price_unit * currency.with_context(dict(self._context or {}, date=self.invoice_id.date_invoice)).rate

				if self.uom_id and self.uom_id.id != product.uom_id.id:
					self.price_unit = product.uom_id._compute_price(self.price_unit, self.uom_id)
		return {'domain': domain}

class AccountInvoiceDocRelLine(models.Model):
	_name='account.invoice.documentorelacionado.line'

	invoice_id = fields.Many2one('account.invoice',ondelete='cascade', index=True)
	
	sequence = fields.Integer(default=10)	
	doc_rel_id = fields.Many2one('documentos.relacionados', required=True)
	nro_docrel = fields.Char(required=True)
	company_id = fields.Many2one('res.company', related='invoice_id.company_id', string='Compañia', store=True, readonly=True)

class AccountInvoiceGuiaLine(models.Model):
	_name='account.invoice.guia.line'

	factura_id = fields.Many2one('account.invoice', ondelete='cascade', index=True)
	
	sequence = fields.Integer(default=10)	
	tip_doc_id = fields.Many2one('tipo.documento', required=True)
	serie_guia = fields.Char(required=True)
	nro_guia = fields.Char(required=True)
	company_id = fields.Many2one('res.company', related='factura_id.company_id', string='Compañia', store=True, readonly=True)
