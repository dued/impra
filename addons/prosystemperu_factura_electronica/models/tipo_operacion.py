# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class TipoOperacion(models.Model):
	_name='tipo.operacion'

	codigo = fields.Char()
	name= fields.Char()
	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)
	