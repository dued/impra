# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class HerenciaMoneda(models.Model):
	_inherit='res.currency'

	descripcion = fields.Char()