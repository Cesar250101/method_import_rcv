# -*- coding: utf-8 -*-

from numpy import require
from pandas import concat
from pyparsing import line
from odoo import api, exceptions, fields, models, _
import base64
import xlrd
import io
from odoo.tools import pycompat
from odoo.exceptions import ValidationError
from datetime import datetime
import requests
import json
from odoo.exceptions import Warning

class Invoice_wizard(models.TransientModel):
    _name = 'invoice.rcv.wizard'

    type = fields.Selection([('out_invoice', 'Facturas de Clientes'), ('in_invoice', 'Facturas de Proveedores')], string='Tipo')
    product_id = fields.Many2one(comodel_name='product.product', string='Producto por Defecto')
    periodo_libro_id = fields.Many2one(comodel_name='wizard.periodo.libro', string='Periodo Libro (YYYYMM)')
    validar_documentos = fields.Boolean(string='Validar Documentos?')

    @api.model
    def _get_rcv(self,url,company):
        payload = json.dumps({
            "RutUsuario": company.rut_usuario_sii.replace(".",""),
            "PasswordSII": company.password_si,
            "RutEmpresa": company.document_number.replace(".",""),
            "Ambiente": 1,
            "Detallado": True
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': company.simple_api_token
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        return response       

    @api.multi
    def Import_rcv(self):
        Partner = self.env['res.partner']
        #Log = self.env['log.management']
        Currency = self.env['res.currency']
        Product = self.env['product.product']
        Uom = self.env['uom.uom']
        Tax = self.env['account.tax']
        User=self.env['res.users']
        Team = self.env['crm.team']
        Account = self.env['account.account']
        Account_type = self.env['account.account.type']
        Term=self.env['account.payment.term']
        Uom_categ=self.env['uom.category']
        inv_result = {}
        
        invoice_obj = self.env['account.invoice']
        company=self.env.user.company_id
        year=self.periodo_libro_id.name[:4]
        month=self.periodo_libro_id.name[-2:]
        if self.type=='out_invoice':
            url = company.simple_api_servidor_servicios+"/api/RCV/ventas/"+ month +"/"+year
        else:
            url = company.simple_api_servidor_servicios+"/api/RCV/compras/"+ month +"/"+year

        request_rcv=self._get_rcv(url,company)
        if request_rcv.status_code==200:
            request_rcv=json.loads(request_rcv.text)
            if self.type=='out_invoice':
                request_rcv=request_rcv['ventas']['detalleVentas']
            else:
                request_rcv=request_rcv['compras']['detalleCompras']
        else:
            raise Warning("Problemas de conexión al SII!")
        for row in request_rcv:
            if row['tipoDTE']==48:
                break
#            Partner 
            vat =row['rutCliente'] if self.type=='out_invoice' else row['rutProveedor']
            vat=vat.replace('-','').replace('.','')
            vat="CL"+str(vat)

            if self.type=='out_invoice':
                partner_id = Partner.search([('vat', '=', vat),('active','=',True),('customer','=',True)],limit=1)
            else:
                partner_id = Partner.search([('vat', '=', vat),('active','=',True),('supplier','=',True)],limit=1)
            if not partner_id:
                value={'name':row['razonSocial'],
                            'customer':True,
                            'supplier':False,
                            'company_type':'company',
                            'vat':vat,
                            'document_number':row['rutCliente']
                        }
                if self.type=='out_invoice':
                    value["customer"]= True
                    value["supplier"]= False
                    partner_id=Partner.create(value)
                    partner=partner_id
                else:
                    value["customer"]= False
                    value["supplier"]= True
                    partner_id=Partner.create(value)
                    partner=partner_id

#           Salesperson             
            user_id=self.env.uid
                        
#           Search if not found it will create if create option is selected
            team_id=self.env['crm.team'].search([('id','=',1)]).id                        
#           Search if not found it will create if create option is selected
            try:
                date=row['fechaEmision']
            except:
                date=row['fechaRecepcion']
            journal_id=0
            if self.type=="out_invoice":
                journal_id=self.env['account.journal'].search([('type','=','sale')],limit=1)
            else:    
                journal_id=self.env['account.journal'].search([('type','=','purchase')],limit=1)
#           Tipo de documentos
            document_class=self.env['sii.document_class'].search([('sii_code','=',row['tipoDTE'])],limit=1).id
            journal_document_class=self.env['account.journal.sii_document_class'].search([('sii_document_class_id','=',document_class)],limit=1)

            line_vals = []

#           Producto por Defecto
            try:
                if partner_id.product_id:
                    product_id=partner_id.product_id
                else:
                    product_id=self.product_id
            except:
                product_id=self.product_id
#           Obtiene cuenta por defecto desde el partner   
            account_id=False                
            if partner_id.cuenta_id:
                account_id=partner_id.cuenta_id.id
            if not account_id:
                account_id=self.product_id.categ_id.property_account_expense_categ_id.id

#           Impuestos            
            if row['montoIvaRecuperable']!='0':
                if self.type=="out_invoice":
                    taxes_ids=self.env['account.tax'].search([('sii_code','=',14),('type_tax_use','=','sale')],limit=1).id
                else:
                    taxes_ids=self.env['account.tax'].search([('sii_code','=',14),('type_tax_use','=','purchase')],limit=1).id
            if  row['montoExento']!=0:
                if self.type=="out_invoice":
                    taxes_ids_exento=self.env['account.tax'].search([('amount','=',0),('type_tax_use','=','sale')],limit=1).id
                else:
                    taxes_ids_exento=self.env['account.tax'].search([('amount','=',0),('type_tax_use','=','purchase')],limit=1).id
#Impuestos Adicionales   
            otros_impuestos=0
            if row['totalOtrosImpuestos']!=0:
                otros_impuestos=int(row['totalOtrosImpuestos'])
                            
            if row['montoNeto']!='0':
                line_vals.append((0,0,{
                    'product_id':product_id.id,
                    'name':product_id.name,
                    'quantity':1,
                    'uom_id':product_id.uom_id.id,
                    'price_unit':row['montoNeto'],
                    'invoice_line_tax_ids':[(6,0,[taxes_ids])],
                    'account_id':account_id
                }))
            if row['montoExento']!=0:
                line_vals.append((0,0,{
                    'product_id':product_id.id,
                    'name':product_id.name,
                    'quantity':1,
                    'uom_id':product_id.uom_id.id,
                    'price_unit':row['montoExento'],
                    'invoice_line_tax_ids':[(6,0,[taxes_ids_exento])],
                    'account_id':account_id
                }))

            if otros_impuestos>0:

                line_vals.append((0,0,{
                    'product_id':product_id.id,
                    'name':'Otros Impuestos',
                    'quantity':1,
                    'uom_id':product_id.uom_id.id,
                    'price_unit':otros_impuestos,
                    'invoice_line_tax_ids':[(6,0,[taxes_ids_exento])],
                    'account_id':account_id
                }))

            neto=round(row['montoNeto'])
            impuesto=int(row['montoIvaRecuperable'])
            if self.type=='out_invoice':
                type='out_invoice'
                if row['tipoDTE']=='61':
                    type='out_refund'
            elif self.type=='in_invoice':
                type='in_invoice'
                if row['tipoDTE']=='61':
                    type='in_refund'
            factura={
                'partner_id': partner_id.id,
                'user_id':user_id,
                'team_id':team_id,
                'journal_id':journal_id.id,
                'date_invoice': date,
                'type': type,
                'document_class_id':document_class,
                'journal_document_class_id':journal_document_class.id,
                'sii_code':row['tipoDTE'],
                'sii_document_number':row['folio'],
                'invoice_line_ids':line_vals,
                'reference':row['folio'],
                'amount_untaxed':neto,
                'amount_untaxed_signed':neto,
                'amount_tax':impuesto,
                'amount_total':row['montoTotal'],
                'amount_total_signed':row['montoTotal'],
                'amount_total__company_signed':row['montoTotal'],
                'periodo_libro':self.periodo_libro_id.id
            }
            factura_existe=self.env['account.invoice'].search([('sii_document_number','=',row['folio']),('partner_id','=',partner_id.id)])
            if not factura_existe:
                invoice_var = invoice_obj.create(factura)
                if journal_id.type=='sale':
                    if self.validar_documentos:
                        journal_id.restore_mode=True
                        invoice_var.action_invoice_open()
        if self.type=='out_invoice':
            journal_id.restore_mode=False                
        return True