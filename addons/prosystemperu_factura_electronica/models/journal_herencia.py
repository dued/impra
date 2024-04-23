# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime,timedelta,date
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
import logging
_logger = logging.getLogger(__name__)

class JournalHerencia(models.Model):
	_inherit='account.journal'
	direccion = fields.Char()
	state_id = fields.Many2one('res.country.state')
	provincia_id = fields.Many2one('res.provincia')
	distrito_id = fields.Many2one('res.distrito')