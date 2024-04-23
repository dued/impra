# -*- coding: utf-8 -*-
from odoo import http

# class Agregacampo(http.Controller):
#     @http.route('/agregacampo/agregacampo/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/agregacampo/agregacampo/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('agregacampo.listing', {
#             'root': '/agregacampo/agregacampo',
#             'objects': http.request.env['agregacampo.agregacampo'].search([]),
#         })

#     @http.route('/agregacampo/agregacampo/objects/<model("agregacampo.agregacampo"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('agregacampo.object', {
#             'object': obj
#         })