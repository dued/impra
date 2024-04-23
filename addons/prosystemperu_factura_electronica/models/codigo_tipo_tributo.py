# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class CodigoTipoTributo(models.Model):
	_name='codigo.tipo.tributo'

	codigo = fields.Char()
	name= fields.Char()
	codigo_internacional= fields.Char()
	nombre= fields.Char()
	categoria= fields.Char()
	