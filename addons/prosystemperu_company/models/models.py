# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
import base64


	
class HerenciaCompany(models.Model):
	_inherit = 'res.company'
		
	logo_ultimo=fields.Binary(compute='traer_binary', store=True)
	url_webservice=fields.Char()

	pag_custodia = fields.Char()
	cuenta_detracciones = fields.Char()

	ocultar_logo=fields.Boolean(default=False)
	texto_logo = fields.Char()

	url_webservice_facturacion = fields.Char()

	certificado_pfx = fields.Binary()	
	certificado_fname= fields.Char()
	password_certificado = fields.Char()

	usuario_sunat = fields.Char()
	password_sunat = fields.Char()
	tipo_facturacion = fields.Selection([('1','Modo prueba'),('2','Modo producción')],default="1")

	igv_facturacion = fields.Float()	
	
	rubro_empresa = fields.Char()
	imprimir_comprobante = fields.Boolean(help="Si esta marcado se imprimira los reportes en pdf, sino imprima el ticket en el punto de venta ")

	modo_envio_documento = fields.Selection([('manual','Manual'),('validar','Al validar'),('programado','Programado')],
		help=" * La opción 'Manual' se utiliza en el cuando queramos que el proceso Facturación electrónica lo realice por partes.\n"
			" * La opción 'Al validar' se utiliza cuando queramos que el proceso Facturación electrónica lo realice al validar el documento.\n"
			" * La opción 'Programado' se utiliza cuando queramos que un proceso automatico realice todo el proceso de la Facturación electrónica a una hora programada .\n")

	bd_custodia = fields.Char()
	#texto_prueba=fields.Text()
	#ejecuta=fields.Selection([('si','EJECUTA'),('no','NO EJECUTA')])

	@api.one
	@api.depends('logo','partner_id.image')
	def traer_binary(self):
		for company in self:
			company.logo_ultimo=company.logo or company.partner_id.image

	


	'''@api.onchange('ejecuta')
	def ejecuta_prueba(self):
		if self.ejecuta=="si":
			#self.env.cr.execute("""UPDATE res_company set certificado_cadena=certificado_pfx::text ;SELECT certificado_cadena  from res_company""")
			data=self.env['res.company'].browse(1)


			self.texto_prueba = str(data.certificado_pfx)







					
			self.env.cr.execute("""SELECT to_json (a) from (select * from account_invoice order by id desc limit 3) a """)
			byte_pdf=self.env.cr.fetchall()
			self.texto_prueba = str(byte_pdf)'''
