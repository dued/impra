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



class FacturaBaja(models.Model):
	_name='factura.baja'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	@api.one
	@api.depends('fac_baja_linea.importe_total')
	def _compute_total_baja(self):        
		self.total_fac_bajas = sum(line.importe_total for line in self.fac_baja_linea)

	name = fields.Char()
	fecha_baja = fields.Date(string="Fecha de baja", default=fields.Date.context_today, track_visibility='always')
	fecha_doc = fields.Date(string="Fecha emisión de factura",track_visibility='always')	
	state = fields.Selection([('borrador','Borrador'),('generado','Generado'),('enviado','Enviado'),('aceptado','Aceptado'),('rechazado','Rechazado')], string='Estado',default="borrador", track_visibility='onchange')		
	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)
	nro_ticket_sunat = fields.Char()
	mensaje_estado = fields.Char(readonly=True)
	xml_firmado=fields.Binary()
	xml_firmado_filename=fields.Char()
	xml_cdr=fields.Binary(help="Constancia de Recepción.")
	xml_cdr_filename=fields.Char()
	fac_baja_linea = fields.One2many('factura.baja.line', 'fac_baja_id', string="Detalle" )
	total_fac_bajas = fields.Float(string="Total", compute='_compute_total_baja', store=True, track_visibility='always')
	motivo_baja = fields.Char(default="BAJA")
	#prueba_texto = fields.Text()

	_sql_constraints = [('name_uniq', 'unique(name)', 'El nombre de las Facturas de bajas deben ser unicos!'),]


	@api.multi
	def agregar_cpe(self):
		return{
		'view_mode': 'form',
		#'res_id': mi_id,
		'res_model': 'wizard.cpe',
		'view_type': 'form',
		'type': 'ir.actions.act_window',
		'target': 'new',
		'flags': {'action_buttons': False},		
		}

	
	@api.onchange('fac_baja_linea')
	def numeracion_item(self):
		if not self.fac_baja_linea:
			return
		numeracion = 0
		for linea in self.fac_baja_linea:
			numeracion += 1
			linea.item = numeracion	

	@api.model
	def create(self, vals):       
		data = super(FacturaBaja, self).create(vals)		
		data.obtiene_name()		
		return data


	@api.multi
	def unlink(self):
		for invoice in self:
			if invoice.state not in ('borrador', 'generado'):
				raise UserError(_('Solo se puede eliminar los registros que estan en borrador o generado.'))	        
		return super(FacturaBaja, self).unlink()


	@api.constrains('fecha_baja','fecha_doc','fac_baja_linea')
	def _restringuiendo_fecha_baja(self):
		
		if not self.fecha_baja:
			raise ValidationError(_('Ingrese fecha de la baja de facturas'))

		if not self.fecha_doc:
			raise ValidationError(_('Ingrese fecha de las boletas a procesar'))

		for data in self:
			fecha = data.fecha_doc			
			date_doc = datetime.strptime(fecha, '%Y-%m-%d').date()
			fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			
			
			fecha_actual_str=str(fecha_actual)
			
			'''if not self.fac_baja_linea:
				raise ValidationError(_('El regitro no tiene ninguna Factura de baja en el detalle'))'''
	

	@api.one			
	def obtiene_name(self):

		fechabaja = self.fecha_baja.replace('/','').replace('-','') 

		self.env.cr.execute("""SELECT ('RA-%s-'||(numero + 1)::text)::text num 
							from(
							SELECT coalesce(max(substring(name, 13)::integer), 0) numero 
							FROM factura_baja 
							where fecha_baja = '%s') dato"""% (fechabaja,fechabaja))

		self.name = str(self.env.cr.fetchall()[0][0])

	@api.multi
	@api.onchange('fecha_doc','motivo_baja')
	def _agrega_facturas_detalle(self):
		if not self.fecha_doc:
			self.fac_baja_linea = False
			return

		if not self.motivo_baja:
			self.fac_baja_linea = False
			return

		
		fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			
		fecha_validar = fecha_actual-timedelta(days=77)
		ids_factura = self.env['account.invoice'].search([('date_invoice','=', self.fecha_doc),('state','=', 'anulado'),('serie','like', 'F'),('estado_invoice_xml','=', 'aceptado'),('fecha_enviado_sunat','>=',date.strftime(fecha_validar,"%Y-%m-%d"))], order="id asc")
		
		result = []
		numeracion = 0
		for linea in ids_factura:
			if not linea.motivo_anulacion:
				linea.motivo_anulacion = self.motivo_baja
				
			numeracion += 1
			result.append((0,0 , {'item': numeracion,'id_factura': linea.id,'motivo_fac_baja': linea.motivo_anulacion ,'tipo_documento': linea.tipo_doc, 'serie_documento': linea.serie, 'numeracion_documento': linea.numeracion,'fecha_emision_documento': linea.date_invoice,'importe_total': linea.amount_total }))
		self.fac_baja_linea = result

		
	@api.multi
	def generando_json(self):

		xjson = []
		# cabecera
		self.env.cr.execute("""SELECT to_json(data) from(
						select to_char(a.fecha_baja, 'YYYY-MM-DD') fechaemision, to_char(a.fecha_doc, 'YYYY-MM-DD') fechareferencia,
						COALESCE(a.name,'')::varchar iddocumento															
						from factura_baja a										
						where a.id =%s) data"""% self.id)

		lcab = self.env.cr.fetchall()[0][0]

		#Emisor o Company
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT COALESCE(c.tipo_documento,'') tipodocumento,COALESCE(c.vat,'') nrodocumento, COALESCE(c.name,'') nombrelegal,COALESCE(c.nombre_comercial,'') nombrecomercial,
							'0000'::varchar coddomfiscal,COALESCE(d.code,'')::varchar(6) ubigeo,
							COALESCE(c.urbanizacion,'')::varchar urbanizacion,COALESCE(f.name,'')::varchar departamento,
							COALESCE(e.name,'')::varchar provincia, COALESCE(d.name,'')::varchar distrito,COALESCE(c.street,'')::varchar direccion							
							from factura_baja a
							left join res_company b on b.id=a.company_id
							left join res_partner c on c.id=b.partner_id
							left join res_distrito d on d.id=c.distrito_id
							left join res_provincia e on e.id=c.provincia_id
							left join res_country_state f on f.id=c.state_id							
							where a.id=%s) data"""% self.id)

		lemisor = self.env.cr.fetchall()[0][0]		
		lcab['emisor']= lemisor		

		#Detalle
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT a.item id,
							case b.tipo_doc when 'FAC' then '01' when 'BOL' then '03' when 'NCR' then '07' when 'NDB' then '08' else 'XX' end::varchar(2) tipodocumento, 
							COALESCE(b.serie,'')::varchar serie,					 
							COALESCE(b.numeracion,'')::varchar correlativo,
							COALESCE(a.motivo_fac_baja,'')::varchar motivobaja						
							from factura_baja_line a
							left join account_invoice b on b.id=a.id_factura
							left join res_currency c on c.id=b.currency_id
							left join res_partner d on d.id=b.partner_id																				
							where a.fac_baja_id=%s) data"""% self.id)

		ldet = self.env.cr.fetchall()

		y = []
		for item in ldet:
			y.append(item[0])		

		lcab['bajas']=y
		xjson.append(lcab)		

		return xjson

	@api.multi
	def crear_xml_baja(self,p_client):		

		json = self.generando_json()

		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"

		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())
		
		cXml = p_client.service.CrearXmlBaja("C://prosystem/XML_SINFIRMA/", json_nombre, str(zip_base64))
		
		return cXml

	@api.multi
	def firmar_xml_baja(self,p_client):
		data=self.env['res.company'].browse(self.company_id.id)
		cad_pfx = str(data.certificado_pfx)
		cadena_pfx= cad_pfx[2:len(cad_pfx)-1]

		cXml = self.crear_xml_baja(p_client)

		extension2=False
		

		cXmlFirmado = p_client.service.FirmarXmlBaja(cXml, cadena_pfx, self.company_id.password_certificado,extension2)

		return cXmlFirmado

	@api.multi
	def enviar_xml_baja(self):

		if not self.company_id.url_webservice_facturacion:
			return

		if not self.fac_baja_linea:
			raise ValidationError(_('El regitro no tiene ninguna factura en el detalle'))

		#ruta_archivo_xml="C://prosystem/XML/"
		nombre_archivo="%s-%s"% (self.company_id.vat, self.name)

		
		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)

		cXmlFirmado = self.firmar_xml_baja(client)

		self.xml_firmado = cXmlFirmado	

		ruta_archivo_xml="C://prosystem/CDR/"
		cCDR = client.service.EnviarXmlBaja(cXmlFirmado,ruta_archivo_xml,nombre_archivo,self.company_id.usuario_sunat,self.company_id.password_sunat,self.company_id.tipo_facturacion)
		#_logger.info("CDR:" + cXmlFirmado)		
		
		diccionario=ast.literal_eval(cCDR)

		self.nro_ticket_sunat = diccionario['NroTicket']
		self.mensaje_estado = diccionario['mensaje']		
		
		self.xml_firmado = cXmlFirmado
		self.xml_firmado_filename = nombre_archivo + ".xml"		
		
		self.state ="enviado"		

	@api.multi
	def consultar_ticket_baja(self):
		ruta_archivo_xml="C://prosystem/XML/"
		nombre_archivo="%s-%s.xml"% (self.company_id.vat, self.name)

		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)
		cCDR = client.service.ConsultarTicketBaja(self.nro_ticket_sunat,ruta_archivo_xml,nombre_archivo,self.company_id.usuario_sunat,self.company_id.password_sunat,self.company_id.tipo_facturacion)
		#_logger.info("CDR:" + cXmlFirmado)
		_logger.info("CDR:" + str(cCDR) )
		cCDR2=cCDR.replace("'",'"').replace('{"',"{'").replace('": "',"': '").replace('"}',"'}").replace('", "cdr":"',"', 'cdr':'")
		
		diccionario=ast.literal_eval(cCDR2)

		self.mensaje_estado=diccionario['mensaje']			

		if not  diccionario.get('cdr'):
			return
		
		self.xml_cdr = diccionario['cdr']
		self.xml_cdr_filename = "R-" + nombre_archivo
		self.state = "aceptado"

		for item in self.fac_baja_linea:
			cMsg = "El comprobante electrónico " + item.id_factura.serie + "-" + item.id_factura.numeracion + " fue comunicado de baja el %s."% (self.fecha_baja[8:]+'/' + self.fecha_baja[5:7]  + '/' + self.fecha_baja[0:4]) 
			oBol = self.env['account.invoice'].browse(item.id_factura.id).write({'estado_invoice_xml': 'baja', 'estado_factura_xml': cMsg, 'state': 'anulado'})



class FacturaBajaLine(models.Model):
	_name='factura.baja.line'

	fac_baja_id = fields.Many2one('factura.baja',ondelete='cascade')

	fecha_doc_cabecera = fields.Date(related="fac_baja_id.fecha_doc")
	item = fields.Integer()
	id_factura = fields.Many2one('account.invoice')
	motivo_fac_baja	= fields.Char()
	tipo_documento = fields.Char()
	serie_documento = fields.Char()
	numeracion_documento = fields.Char()
	fecha_emision_documento = fields.Date()		
	importe_total = fields.Float()


	_sql_constraints = [('id_factura_uniq', 'unique(id_factura)', 'Las facturas de bajas del detalle deben ser unicos!'),]

	@api.multi
	@api.onchange('id_factura')
	def _agrega_facturas_detalle(self):
		if not self.fac_baja_id:
			return

		if not self.fac_baja_id.fecha_doc:
			warning = {
			'title': _('¡Alerta!'),
			'message': _('¡Primero debe selecccionar la fecha de el(los) factura(s) a dar de baja!'),
			}
			return {'warning': warning}

		self.tipo_documento = self.id_factura.tipo_doc
		self.serie_documento = self.id_factura.serie
		self.numeracion_documento = self.id_factura.numeracion
		self.fecha_emision_documento = self.id_factura.date_invoice		
		self.importe_total = self.id_factura.amount_total
		self.motivo_fac_baja = self.fac_baja_id.motivo_baja		
