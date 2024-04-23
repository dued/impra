# -*- coding: utf-8 -*-

from odoo import _, models, fields, api

class HerenciaDepartamento(models.Model):
	_inherit='res.country.state'

	provincia_ids = fields.One2many('res.provincia', 'departamento_id')
	company_id = fields.Many2one('res.company', 'Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)


	
class ResProvincia(models.Model):
	_name='res.provincia'

	departamento_id = fields.Many2one('res.country.state')

	name = fields.Char()
	code = fields.Char()
	company_id = fields.Many2one('res.company', 'Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)

	distrito_ids = fields.One2many('res.distrito', 'provincia_id')

class ResDistrito(models.Model):
	_name='res.distrito'

	provincia_id = fields.Many2one('res.provincia')

	name = fields.Char()
	code = fields.Char()
	company_id = fields.Many2one('res.company', 'Compañia', required=True, index=True, default=lambda self: self.env.user.company_id.id)


# class nombremodulo(models.Model):
#     _name = 'nombremodulo.nombremodulo'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         self.value2 = float(self.value) / 100