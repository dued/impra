# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
from datetime import datetime,timedelta,date
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import logging
_logger = logging.getLogger(__name__)

class WizardAnulacion(models.TransientModel):
	_name = 'wizard.anulacion'
	
	motivo_anula = fields.Char()	

	def enviar_registro(self):	
		context = dict(self._context or {})
		data = self.env['account.invoice'].browse(context.get('active_ids'))

		for baja in data:
			#_logger.info('fecha_prueba:' + str(fields.Datetime.context_timestamp(self, datetime.strptime(baja.fecha_enviado_sunat, DEFAULT_SERVER_DATETIME_FORMAT)).date())) #obtiene la fecha con zona horario del servidor									
			fecha_actual = fields.Datetime.context_timestamp(self, datetime.strptime(fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)).date()			

			if not baja.fecha_enviado_sunat:
				fecha_envio = fecha_actual
			else:
				fecha_envio = fields.Datetime.context_timestamp(self, datetime.strptime(baja.fecha_enviado_sunat, DEFAULT_SERVER_DATETIME_FORMAT)).date()			
			
			if fecha_envio >= fecha_actual - timedelta(days=77):
				baja.motivo_anulacion = self.motivo_anula
				baja.state = 'anulado'
			else:
				raise ValidationError(_('No se puede Anular el comprobante, ya pasaron más de 7 días de su fecha de envío a sunat'))

	

    
 
