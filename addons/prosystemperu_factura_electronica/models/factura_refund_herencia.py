# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
from datetime import datetime,timedelta,date
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning



class HerenciaFacturaRectificativa(models.TransientModel):
	_inherit='account.invoice.refund'


	def _domain_motivo(self):
		ids_motivo=[]
		context = dict(self._context or {})
		for inv in self.env['account.invoice'].browse(context.get('active_ids')):
			
			if inv.tipo_doc == 'BOL':
				ids_filtrado=self.env['rectificativa.motivo'].search([('codigo','in',('01','02','03','06','07', '09'))])
				for data in ids_filtrado:
					ids_motivo.append(data.id)
			elif inv.tipo_doc == 'FAC':
				ids_filtrado=self.env['rectificativa.motivo'].search([])
				for data in ids_filtrado:
					ids_motivo.append(data.id)
		return ids_motivo		


	rectificativa_motivo = fields.Many2one('rectificativa.motivo', domain=lambda self: [('id', 'in', self._domain_motivo())])


	
	@api.multi
	def compute_refund(self, mode='refund'):
		inv_obj = self.env['account.invoice']
		inv_tax_obj = self.env['account.invoice.tax']
		inv_line_obj = self.env['account.invoice.line']
		context = dict(self._context or {})
		xml_id = False

		for form in self:
			created_inv = []
			date = False
			description = False
			for inv in inv_obj.browse(context.get('active_ids')):
				if inv.state in ['draft', 'cancel']:
					raise UserError(_('Cannot create credit note for the draft/cancelled invoice.'))
				if inv.reconciled and mode in ('cancel', 'modify'):
					raise UserError(_('Cannot create a credit note for the invoice which is already reconciled, invoice should be unreconciled first, then only you can add credit note for this invoice.'))

				date = form.date or False
				description = form.description or inv.name
				tipo_nota_credito = form.rectificativa_motivo.id 
				refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id, tipo_nota_credito)

				created_inv.append(refund.id)
				if mode in ('cancel', 'modify'):
					movelines = inv.move_id.line_ids
					to_reconcile_ids = {}
					to_reconcile_lines = self.env['account.move.line']
					for line in movelines:
						if line.account_id.id == inv.account_id.id:
							to_reconcile_lines += line
							to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
						if line.reconciled:
							line.remove_move_reconcile()
					refund.action_invoice_open()
					for tmpline in refund.move_id.line_ids:
						if tmpline.account_id.id == inv.account_id.id:
							to_reconcile_lines += tmpline
					to_reconcile_lines.filtered(lambda l: l.reconciled == False).reconcile()
					if mode == 'modify':
						invoice = inv.read(inv_obj._get_refund_modify_read_fields())
						invoice = invoice[0]
						del invoice['id']
						invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
						invoice_lines = inv_obj.with_context(mode='modify')._refund_cleanup_lines(invoice_lines)
						tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
						tax_lines = inv_obj._refund_cleanup_lines(tax_lines)
						invoice.update({
							'type': inv.type,
							'date_invoice': form.date_invoice,
							'state': 'draft',
							'number': False,
							'invoice_line_ids': invoice_lines,
							'tax_line_ids': tax_lines,
							'date': date,
							'origin': inv.origin,
							'fiscal_position_id': inv.fiscal_position_id.id,
						})
						for field in inv_obj._get_refund_common_fields():
							if inv_obj._fields[field].type == 'many2one':
								invoice[field] = invoice[field] and invoice[field][0]
							else:
								invoice[field] = invoice[field] or False
						inv_refund = inv_obj.create(invoice)
						if inv_refund.payment_term_id.id:
							inv_refund._onchange_payment_term_date_invoice()
						created_inv.append(inv_refund.id)
				xml_id = inv.type == 'out_invoice' and 'action_invoice_out_refund' or \
						inv.type == 'out_refund' and 'action_invoice_tree1' or \
						inv.type == 'in_invoice' and 'action_invoice_in_refund' or \
						inv.type == 'in_refund' and 'action_invoice_tree2'
				# Put the reason in the chatter
				subject = _("Credit Note")
				body = description
				refund.message_post(body=body, subject=subject)
		if xml_id:
			result = self.env.ref('account.%s' % (xml_id)).read()[0]
			invoice_domain = safe_eval(result['domain'])
			invoice_domain.append(('id', 'in', created_inv))
			result['domain'] = invoice_domain
			return result
		return True





