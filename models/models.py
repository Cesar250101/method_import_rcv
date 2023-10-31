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



class Invoice_wizard(models.TransientModel):
    _name = 'invoice.rcv.wizard'

    data_file = fields.Binary(string="File")
    type = fields.Selection([('out_invoice', 'Facturas de Clientes'), ('in_invoice', 'Facturas de Proveedores')], string='Tipo')
    product_id = fields.Many2one(comodel_name='product.product', string='Producto por Defecto')
    periodo_libro_id = fields.Many2one(comodel_name='wizard.periodo.libro', string='Periodo Libro')
    

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
        
        
        file_data = False
        if self.data_file and self.type:
            try:
                csv_reader_data = pycompat.csv_reader(io.BytesIO(base64.decodestring(self.data_file)),quotechar=",",delimiter=",")
                csv_reader_data = iter(csv_reader_data)
                next(csv_reader_data)
                file_data = csv_reader_data
            except:
                raise exceptions.Warning(_('Please select proper file type.'))
        else:
            raise exceptions.Warning(_('Please select all the required fields.'))
        for row in file_data:
#            Partner 
            linea=row[0]
            linea=linea.split(";")
            vat =linea[3]
            vat=vat.replace('-','').replace('.','')
            vat="CL"+str(vat)

            if self.type=='out_invoice':
                partner_id = Partner.search([('vat', '=', vat),('active','=',True),('customer','=',True)],limit=1)
            else:
                partner_id = Partner.search([('vat', '=', vat),('active','=',True),('supplier','=',True)],limit=1)
            if not partner_id:
                if self.type=='out_invoice':
                    partner_id=Partner.create(
                            {'name':linea[4],
                            'customer':True,
                            'supplier':False,
                            'company_type':'company',
                            'vat':vat,
                            'document_number':linea[3]
                            })
                    partner=partner_id
                else:
                    partner_id=Partner.create(
                        {'name':linea[4],
                        'supplier':True,
                        'customer':False,
                        'company_type':'company',
                        'vat':vat,
                        'document_number':linea[3]

                        })
                    partner=partner_id

#           Salesperson             
            user_id=self.env.uid
                        
#           Search if not found it will create if create option is selected
            team_id=self.env['crm.team'].search([('id','=',1)]).id                        
#           Search if not found it will create if create option is selected
            try:
                date=datetime.strptime(linea[6], '%d-%m-%Y').strftime('%Y-%m-%d')
            except:
                date=datetime.strptime(linea[6], '%d/%m/%Y').strftime('%Y-%m-%d')
            journal_id=0
            if self.type=="out_invoice":
                journal_id=self.env['account.journal'].search([('type','=','sale')],limit=1)
            else:    
                journal_id=self.env['account.journal'].search([('type','=','purchase')],limit=1)
#           Tipo de documentos
            document_class=self.env['sii.document_class'].search([('sii_code','=',linea[1])],limit=1).id
            journal_document_class=self.env['account.journal.sii_document_class'].search([('sii_document_class_id','=',document_class)],limit=1)

            line_vals = []

#            Producto por Defecto
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
            if self.type=="out_invoice":
                taxes_ids=self.env['account.tax'].search([('sii_code','=',14),('type_tax_use','=','sale')],limit=1).id
            else:
                taxes_ids=self.env['account.tax'].search([('sii_code','=',14),('type_tax_use','=','purchase')],limit=1).id

            if self.type=="out_invoice" and linea[10]!='0' and linea[10]!='':
                taxes_ids_exento=self.env['account.tax'].search([('amount','=',0),('type_tax_use','=','sale')],limit=1).id
            elif self.type=="in_invoice" and linea[9]!='0' and linea[9]!='':
                taxes_ids_exento=self.env['account.tax'].search([('amount','=',0),('type_tax_use','=','purchase')],limit=1).id
#Impuestos Adicionales   
            otros_impuestos=0
            if linea[25]!="":
                otros_impuestos=int(linea[25])
            precio=0                
            if self.type=="out_invoice":
                precio= float(linea[10])+float((linea[11]))
            else:
                precio=float(linea[9])+float(linea[10])
            line_vals.append((0,0,{
                    'product_id':product_id.id,
                    'name':product_id.name,
                    'quantity':1,
                    'uom_id':product_id.uom_id.id,
                    'price_unit':precio,
                    'invoice_line_tax_ids':[(6,0,[taxes_ids])],
                    'account_id':account_id
                }))


            if otros_impuestos>0:

                line_vals.append((0,0,{
                    'product_id':product_id.id,
                    'name':'Otros Impuestos',
                    'quantity':1,
                    'uom_id':product_id.uom_id.id,
                    'price_unit':otros_impuestos,
                    'invoice_line_tax_ids':[(6,0,[taxes_ids])],
                    'account_id':account_id
                }))

#Referencia si es nota de crédito o nota de débito
            referencia=[]
            if linea[1] in('61','56'):
                domain=[
                        ('sii_document_number','=',linea[25]),
                        ('partner_id','=',partner_id.id)
                    ]
                invoice_ref_id=self.env['account.invoice'].search(domain)
                referencia.append((0,0,{
                            'origen':linea[25],
                            'sii_referencia_TpoDocRef':document_class,
                            'sii_referencia_CodRef':'1',
                            'motivo':"Anula documento",
                            'fecha_documento':date,
                            'invoice_id':invoice_ref_id.id if invoice_ref_id.id else False
                        })) 
            neto=round(int(linea[14])/1.19)
            impuesto=int(linea[14])-round(int(linea[14])/1.19)
            if self.type=='out_invoice':
                type='out_invoice'
                if linea[1]=='61':
                    type='out_refund'
            elif self.type=='in_invoice':
                type='in_invoice'
                if linea[1]=='61':
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
                'sii_code':linea[1],
                'sii_document_number':linea[5],
                'invoice_line_ids':line_vals,
                'reference':linea[5],
                'amount_untaxed':neto,
                'amount_untaxed_signed':neto,
                'amount_tax':impuesto,
                'amount_total':linea[14],
                'amount_total_signed':linea[14],
                'amount_total__company_signed':linea[14],
                'periodo_libro':self.periodo_libro_id.id,
                'referencias':referencia
            }
            factura_existe=self.env['account.invoice'].search([('sii_document_number','=',linea[5]),('partner_id','=',partner_id.id)])
            if not factura_existe:
                invoice_var = invoice_obj.create(factura)
                journal_id.restore_mode=True
                invoice_var.action_invoice_open()
            journal_id.restore_mode=False
        return True