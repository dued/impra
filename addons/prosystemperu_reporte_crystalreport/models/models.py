# -*- coding: utf-8 -*-
#import base64
from odoo import _, models, fields, api

class ReporteCrystalReport(models.Model):
	_name = "reporte.crystalreport"

	nombre_modelo=fields.Char()
	id_registro_modelo= fields.Integer()	
	txt_filename = fields.Char()
	txt_binary = fields.Binary()

	

	


	
	


		





