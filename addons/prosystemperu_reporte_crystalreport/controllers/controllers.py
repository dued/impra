# -*- coding: utf-8 -*-
from odoo import http

# class Nombremodulo(http.Controller):
#     @http.route('/nombremodulo/nombremodulo/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/nombremodulo/nombremodulo/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('nombremodulo.listing', {
#             'root': '/nombremodulo/nombremodulo',
#             'objects': http.request.env['nombremodulo.nombremodulo'].search([]),
#         })

#     @http.route('/nombremodulo/nombremodulo/objects/<model("nombremodulo.nombremodulo"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('nombremodulo.object', {
#             'object': obj
#         })