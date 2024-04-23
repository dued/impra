# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class DocumentosRelacionados(models.Model):
	_name='documentos.relacionados'
	
	codigo = fields.Char()
	name = fields.Char()
	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)
