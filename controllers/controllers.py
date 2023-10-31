# -*- coding: utf-8 -*-
from odoo import http

# class MethodImportRcv(http.Controller):
#     @http.route('/method_import_rcv/method_import_rcv/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/method_import_rcv/method_import_rcv/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('method_import_rcv.listing', {
#             'root': '/method_import_rcv/method_import_rcv',
#             'objects': http.request.env['method_import_rcv.method_import_rcv'].search([]),
#         })

#     @http.route('/method_import_rcv/method_import_rcv/objects/<model("method_import_rcv.method_import_rcv"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('method_import_rcv.object', {
#             'object': obj
#         })