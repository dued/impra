# -*- coding: utf-8 -*-

from odoo import _, models, fields, api


class HerenciaUsuario(models.Model):
	_inherit='res.users'

	journal_ids= fields.Many2many('account.journal', string='journal ids', domain=lambda self: [('type', '=', 'sale'),('company_id', '=', self.env.user.company_id.id)])
	journal_id = fields.Many2one('account.journal', string='Journal default', required=True,domain=lambda self: [('type', '=', 'mostrar vacio')])


	@api.onchange('journal_ids')
	def onchange_usuario_dominio(self):
		result = {}
		todo=[]

		if not self.journal_ids:
			result['domain'] = {'journal_id': [('type', '=', 'mostrar vacio')]}			
			return result
		#self.login=str(self.journal_ids)
		
		for vuelta in self.journal_ids:
			 todo.append(vuelta.id)

	
		
		result['domain'] = {'journal_id': [('id', '=', todo)]}
		return result
