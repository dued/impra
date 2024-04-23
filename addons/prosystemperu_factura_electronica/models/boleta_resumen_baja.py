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



class BoletasResumenBaja(models.Model):
	_name='boleta.resumen.baja'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	@api.one
	@api.depends('boleta_linea.importe_total')
	def _compute_total_resumen(self):        
		self.total_resumen = sum(line.importe_total for line in self.boleta_linea)	

	name = fields.Char()
	fecha_resumen = fields.Date(string='Fecha del resumen diario de boletas',default=fields.Date.context_today,track_visibility='always')
	fecha_documentos = fields.Date(string='Fecha de emisión de las boletas', track_visibility='always')	
	estado_boleta = fields.Selection([('borrador','Borrador'),('generado','Generado'),('enviado','Enviado'),('aceptado','Aceptado'),('rechazado','Rechazado')], track_visibility='onchange', string='Estado deL XML',default="borrador",
		help=" * El estado 'Borrador' es cuando el documento XML no esta creado.\n"
			" * El estado 'Generado' es cuando el documento XML esta creado y firmado .\n"
			" * El estado 'Enviado' es cuando ya se envio a sunat el documento XML firmado y devolvio un número de ticket para consultarlo luego .\n"
			" * El estado 'Aceptado' es cuando ya se envio a sunat el un número de ticket y nos respondio satisfactoriamente el CDR .\n"
			" * El estado 'Rechazado' es cuando ya se envio a sunat el un número de ticket y nos Rechazo el proceso .\n")

	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)

	nro_ticket_sunat = fields.Char()

	mensaje_estado = fields.Char()
	xml_firmado=fields.Binary()
	xml_firmado_filename=fields.Char()
	xml_cdr=fields.Binary(help="Constancia de Recepción.")
	xml_cdr_filename=fields.Char()

	boleta_linea = fields.One2many('boleta.resumen.baja.line', 'resumen_id', string="Detalle Boletas" )

	total_resumen = fields.Float(string='Total resumen diario de boletas',compute='_compute_total_resumen', store=True, track_visibility='always')
	#prueba_texto = fields.Text()
	fecha_enviado_sunat = fields.Datetime()

	_sql_constraints = [('name_uniq', 'unique(name)', 'El nombre de las boletas de resumen diario deben ser unicos!'),]


	@api.multi
	def unlink(self):
		for invoice in self:
			if invoice.estado_boleta not in ('borrador', 'generado'):
				raise UserError(_('Solo se puede eliminar los registros que estan en borrador o generado.'))	        
		return super(BoletasResumenBaja, self).unlink()


	@api.constrains('fecha_resumen','fecha_documentos')
	def _restringuiendo_fecha_resumen(self):
		
		if not self.fecha_resumen:
			raise ValidationError(_('Ingrese fecha del resumen diario de boletas'))

		if not self.fecha_documentos:
			raise ValidationError(_('Ingrese fecha de las boletas a procesar'))

		for data in self:			
			fecha = data.fecha_resumen			
			date_resumen = datetime.strptime(fecha, '%Y-%m-%d').date()

			fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			

			fecha_actual_str=str(fecha_actual)

			if date_resumen > fecha_actual:
				raise ValidationError(_('Ingrese una fecha no mayor a  la fecha actual: %s')% (fecha_actual_str[8:]+'/' + fecha_actual_str[5:7]  + '/' + fecha_actual_str[0:4]))

			'''self.env.cr.execute("""SELECT COALESCE(min(date_invoice),'19000101')::date
							FROM account_invoice 
							where date_invoice < '%s' and tipo_doc = 'BOL' and estado_invoice_xml in ('borrador','generado')"""% self.fecha_documentos)

			fecha_validacion = str(self.env.cr.fetchall()[0][0])
			if fecha_validacion !='1900-01-01':
				raise ValidationError(_('Existen boletas del dia %s sin procesar')% (fecha_validacion[8:]+'/' + fecha_validacion[5:7]  + '/' + fecha_validacion[0:4]))'''

			'''if not self.boleta_linea:
				raise ValidationError(_('El regitro no tiene ninguna boleta en el detalle'))'''

			fecha_doc = data.fecha_documentos			
			date_documento = datetime.strptime(fecha_doc, '%Y-%m-%d').date()
			if date_documento > date_resumen:
				raise ValidationError(_('La fecha de los documentos debe ser menor o igual a la fecha del resumen'))


	@api.model
	def create(self, vals):       
		data = super(BoletasResumenBaja, self).create(vals)		
		data.obtiene_name()
		return data

	@api.one			
	def obtiene_name(self):

		fecharesumen = self.fecha_resumen.replace('/','').replace('-','') 

		self.env.cr.execute("""SELECT ('RC-%s-'||(numero + 1)::text)::text num 
							from(
							SELECT coalesce(max(substring(name, 13)::integer), 0) numero 
							FROM (
							select name from boleta_resumen 
							where fecha_resumen = '%s'
							union all 
							select name from boleta_resumen_baja 
							where fecha_resumen = '%s'
							) res ) dato"""% (fecharesumen,fecharesumen, fecharesumen))

		self.name = str(self.env.cr.fetchall()[0][0])

	@api.onchange('fecha_documentos')
	def _agrega_boletas_detalle(self):
		if not self.fecha_documentos:
			self.fac_baja_linea = False	

		#ids_boletas = self.env['account.invoice'].search([('date_invoice','=', self.fecha_documentos),('tipo_doc','=', 'BOL'),('estado_invoice_xml','in', ('borrador','generado'))], order="id asc", limit=500)
		fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			
		fecha_validar = fecha_actual-timedelta(days=7)
		ids_boletas = self.env['account.invoice'].search([('date_invoice','=', self.fecha_documentos),('state','=', 'anulado'),('tipo_doc','=', 'BOL'),('estado_invoice_xml','=', 'aceptado'),('fecha_enviado_sunat','>=',date.strftime(fecha_validar,"%Y-%m-%d"))], order="id asc")


		result = []
		numeracion = 0
		for line in ids_boletas:
			numeracion += 1
			result.append((0, 0, {'item': numeracion,'id_boleta': line.id,'tipo_documento': line.tipo_doc, 'serie_documento': line.serie, 'numeracion_documento': line.numeracion, 'fecha_emision_documento': line.date_invoice, 'currency_id':line.currency_id, 'estado_documento':line.state, 'importe_total': line.amount_total }))
		self.boleta_linea = result

		
	@api.multi
	def generando_json(self):

		xjson = []
		# cabecera
		self.env.cr.execute("""SELECT to_json(data) from(
						select to_char(a.fecha_resumen, 'YYYY-MM-DD') fechaemision, to_char(a.fecha_documentos, 'YYYY-MM-DD') fechareferencia,
						COALESCE(a.name,'RC-20181114-1')::varchar iddocumento															
						from boleta_resumen_baja a										
						where a.id =%s) data"""% self.id)

		lcab = self.env.cr.fetchall()[0][0]

		#Emisor o Company
		self.env.cr.execute("""SELECT to_json(data) from(
							SELECT COALESCE(c.tipo_documento,'') tipodocumento,COALESCE(c.vat,'') nrodocumento, COALESCE(c.name,'') nombrelegal,COALESCE(c.nombre_comercial,'') nombrecomercial,
							'0000'::varchar coddomfiscal,COALESCE(d.code,'')::varchar(6) ubigeo,
							COALESCE(c.urbanizacion,'')::varchar urbanizacion,COALESCE(f.name,'')::varchar departamento,
							COALESCE(e.name,'')::varchar provincia, COALESCE(d.name,'')::varchar distrito,COALESCE(c.street,'')::varchar direccion							
							from boleta_resumen_baja a
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
							'03'::varchar tipodocumento, (b.serie ||'-'||b.numeracion) iddocumento,
							COALESCE(c.name,'')::varchar moneda, 3::integer codigoestadoitem, 
							COALESCE(d.tipo_documento,'')::varchar TipoDocumentoReceptor, COALESCE(d.vat,'')::varchar nrodocumentoreceptor,
							COALESCE(b.total_operaciones_gravadas,0.00)::numeric(12,2) gravadas,
							COALESCE(b.total_operaciones_exoneradas,0.00)::numeric(12,2) exoneradas,
							COALESCE(b.total_operaciones_inafectas,0.00)::numeric(12,2) inafectas,
							COALESCE(b.total_operaciones_gratuitas,0.00)::numeric(12,2) gratuitas,
							COALESCE(b.total_operaciones_exportadas,0.00)::numeric(12,2) exportacion,
							COALESCE(b.total_otros_cargos,0.00)::numeric(12,2) totalotroscargos, 0.00 totalisc, 
							COALESCE(b.amount_tax, 0.00)::numeric(12,2) totaligv, COALESCE(b.total_otros_tributos, 0.00)::numeric(12,2) totalotrosimpuestos,
							COALESCE(b.amount_total, 0.00)::numeric(12,2) totalventa							
							from boleta_resumen_baja_line a
							left join account_invoice b on b.id=a.id_boleta
							left join res_currency c on c.id=b.currency_id
							left join res_partner d on d.id=b.partner_id																				
							where a.resumen_id=%s) data"""% self.id)

		ldet = self.env.cr.fetchall()

		y = []
		for item in ldet:
			y.append(item[0])		

		lcab['resumenes']=y
		xjson.append(lcab)

		

		return xjson

	@api.multi
	def crear_xml_resumen(self,p_client):		

		json = self.generando_json()


		json_name = ''.join(random.choice(string.ascii_lowercase) for alea in range(10))
		json_nombre= json_name + ".json"


		inMemoryOutputFile = io.BytesIO()
		zipFile = ZipFile(inMemoryOutputFile, mode='w', compression=zipfile.ZIP_DEFLATED) 
		zipFile.writestr('%s'% json_nombre,'%s'% json)
		zipFile.close()
		inMemoryOutputFile.seek(0)
		zip_base64= base64.b64encode(inMemoryOutputFile.getvalue())

		
		cXml = p_client.service.CrearXmlResumen("C://prosystem/XML_SINFIRMA/", json_nombre, str(zip_base64))
		
		return cXml

	@api.multi
	def firmar_xml_resumen(self,p_client):
		data=self.env['res.company'].browse(self.company_id.id)
		cad_pfx = str(data.certificado_pfx)
		cadena_pfx= cad_pfx[2:len(cad_pfx)-1]

		cXml = self.crear_xml_resumen(p_client)

		extension2=False
		

		cXmlFirmado = p_client.service.FirmarXmlResumen(cXml, cadena_pfx, self.company_id.password_certificado,extension2)

		return cXmlFirmado

	@api.multi
	def enviar_xml_resumen(self):

		if not self.company_id.url_webservice_facturacion:
			return

		if not self.boleta_linea:
			raise ValidationError(_('El regitro no tiene ninguna boleta en el detalle'))

		ruta_archivo_xml="C://prosystem/CDR/"
		nombre_archivo="%s-%s"% (self.company_id.vat, self.name)

		
		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)

		cXmlFirmado = self.firmar_xml_resumen(client)

		self.xml_firmado = cXmlFirmado	

		
		cCDR = client.service.EnviarXmlResumen(cXmlFirmado,ruta_archivo_xml,nombre_archivo,self.company_id.usuario_sunat,self.company_id.password_sunat,self.company_id.tipo_facturacion)
		#_logger.info("CDR:" + cXmlFirmado)
		
		
		diccionario=ast.literal_eval(cCDR)

		self.nro_ticket_sunat = diccionario['NroTicket']
		self.mensaje_estado = diccionario['mensaje']		
		
		self.xml_firmado = cXmlFirmado
		self.xml_firmado_filename = nombre_archivo + ".xml"		
		
		self.estado_boleta ="enviado"
			
	@api.multi
	def consultar_ticket(self):
		ruta_archivo_xml="C://prosystem/XML/"
		nombre_archivo="%s-%s.xml"% (self.company_id.vat, self.name)

		client = Client(url='http://%s/Service1.svc?wsdl'% self.company_id.url_webservice_facturacion)
		cCDR = client.service.ConsultarTicket(self.nro_ticket_sunat,ruta_archivo_xml,nombre_archivo,self.company_id.usuario_sunat,self.company_id.password_sunat,self.company_id.tipo_facturacion)
		#_logger.info("CDR:" + cXmlFirmado)
		_logger.info("CDR:" + str(cCDR) )
		cCDR2=cCDR.replace("'",'"').replace('{"',"{'").replace('": "',"': '").replace('"}',"'}").replace('", "cdr":"',"', 'cdr':'")
		
		diccionario=ast.literal_eval(cCDR2)

		self.mensaje_estado=diccionario['mensaje']			

		if not  diccionario.get('cdr'):
			return
		
		self.xml_cdr = diccionario['cdr']
		self.xml_cdr_filename = "R-" + nombre_archivo
		self.estado_boleta ="aceptado"

		for item in self.boleta_linea:
			cMsg = "La boleta número " + item.id_boleta.serie + "-" + item.id_boleta.numeracion + ", fue comunicada de baja el %s."% (self.fecha_resumen[8:]+'/' + self.fecha_resumen[5:7]  + '/' + self.fecha_resumen[0:4]) 
			oBol = self.env['account.invoice'].browse(item.id_boleta.id).write({'estado_invoice_xml': 'baja', 'estado_factura_xml': cMsg})

	def agrega_boletas_detalle_masivo(self):
		self._agrega_boletas_detalle()

		return self

	def enviar_xml_resumen_masivo(self):
		self.enviar_xml_resumen()

		return self

	def CrearResumenDiario(self):
		# Recorrer todas las fechas pendientes de envío.
		
		self.env.cr.execute(""" SELECT distinct date_invoice 
								from account_invoice 
								where date_invoice <= '%s' and tipo_doc = 'BOL' and estado_invoice_xml in('borrador', 'generado') 
								order by date_invoice asc """ % date.today())

		for item in self.env.cr.dictfetchall():
			
			miDic = {'fecha_resumen':date.today(), 'fecha_documentos':item['date_invoice']}
			self.create(miDic).agrega_boletas_detalle_masivo().enviar_xml_resumen_masivo().consultar_ticket()


class BoletaResumenBajaLine(models.Model):
	_name='boleta.resumen.baja.line'

	resumen_id = fields.Many2one('boleta.resumen.baja',ondelete='cascade')

	item = fields.Integer()
	id_boleta = fields.Many2one('account.invoice')
	tipo_documento = fields.Char()
	serie_documento = fields.Char()
	numeracion_documento = fields.Char()
	fecha_emision_documento = fields.Date()
	currency_id = fields.Many2one('res.currency')
	estado_documento = fields.Char()
	importe_total = fields.Float()

	_sql_constraints = [('id_boleta_uniq', 'unique(id_boleta)', 'El id del detalle de boletas de resumen diario deben ser unicos!'),]
