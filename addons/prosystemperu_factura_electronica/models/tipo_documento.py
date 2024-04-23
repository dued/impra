# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class TipoDocumento(models.Model):
	_name='tipo.documento'

	codigo = fields.Char()
	name = fields.Char()
	abreviatura = fields.Char()
	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)
	