# -*- coding: utf-8 -*-

from odoo import _, models, fields, api


class UnidadMedidaSunat(models.Model):
	_name = 'um.sunat'

	codigo_um = fields.Char()
	name = fields.Char()
	abreviatura = fields.Char()
