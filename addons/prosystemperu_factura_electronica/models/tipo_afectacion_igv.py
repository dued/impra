# -*- coding: utf-8 -*-
from odoo import _, models, fields, api

class TipoAfectacionIgv(models.Model):
	_name='tipo.afectacion.igv'
	_rec_name= 'codigo'

	codigo = fields.Char()
	name= fields.Char()
	cod_tip_tributo= fields.Many2one('codigo.tipo.tributo')
	company_id = fields.Many2one('res.company','Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)

	@api.multi
	@api.depends('name', 'codigo')
	def name_get(self):
		result = []
		for data in self:
			name =  str(data.codigo) + ' - ' + str(data.name)
			result.append((data.id, name))
		return result