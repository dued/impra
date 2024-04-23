# -*- coding: utf-8 -*-

from odoo import api, fields, models
from datetime import datetime
from odoo.exceptions import UserError, ValidationError

#sirve para generar el archivo excel
import xlwt
import base64
import io

from suds.client import Client
import ast




class WizardReportCommunalCouncilAdmin(models.TransientModel):
    _name = "factura.reporte.dinamico"
    

    #funcion para capturar los años de facturas validadas en una lista que su contenido son tuplas
    def periodo_buscar(self):
       
        self.env.cr.execute("""SELECT distinct extract(year from fecha_emi_doc_cpe)::text || lpad(extract(month 
                                from fecha_emi_doc_cpe)::text,2,'0') from vw_tbl_cab_cpe order by 1 desc""")
        select_anno= self.env.cr.fetchall()         

        datito=""

        anho=[]         
        
        for line in select_anno:                
            for lineas in line:
                contenido_anho=[]
                primero=""
                segundo=""

                primero=lineas
                segundo= self.get_mes(lineas[4::]) + ' ' + lineas[0:4]

                contenido_anho.append(primero)
                contenido_anho.append(segundo)                                  
                anho.append(tuple(contenido_anho))

        return anho
    #termina funcion para capturar los años de facturas validadas en una lista que su contenido son tuplas
    def get_mes(self,valor):
        if valor == '01':
            return 'ENERO'
        if valor == '02':
            return 'FEBRERO'
        if valor == '03':
            return 'MARZO'
        if valor == '04':
            return 'ABRIL'
        if valor == '05':
            return 'MAYO'
        if valor == '06':
            return 'JUNIO'
        if valor == '07':
            return 'JULIO'
        if valor == '08':
            return 'AGOSTO'
        if valor == '09':
            return 'SEPTIEMBRE'
        if valor == '10':
            return 'OCTUBRE'
        if valor == '11':
            return 'NOVIEMBRE'
        if valor == '12':
            return 'DICIEMBRE'


    #campos en el wizard
    periodo_consulta=fields.Selection(periodo_buscar)
    #mes_consulta = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')])
    
    

    



    #funcion para que llame al reporte
    @api.multi
    def action_excel(self):

        xlwt.easyxf(num_format_str='$#,##0.00')
        
    

        style0 = xlwt.easyxf('font: name Times New Roman, colour red, bold on') 
        style1 = xlwt.easyxf(num_format_str='dd/mm/yyyy')
        style2=xlwt.easyxf(num_format_str='#,##0.00')        
        style3=xlwt.easyxf(num_format_str='#,##0.0000')
        style4=xlwt.easyxf(num_format_str='#,##0')


        wb = xlwt.Workbook()
        ws = wb.add_sheet('A Test Sheet',cell_overwrite_ok=True)

        ws.write(0, 0, 'FEC. EMISION', style0)
        ws.write(0, 1, 'TD', style0)
        ws.write(0, 2, 'SERIE', style0)
        ws.write(0, 3, 'NUEMERO', style0)
        ws.write(0, 4, 'RUC', style0)
        ws.write(0, 5, 'RAZON SOCIAL', style0)
        ws.write(0, 6, 'MONEDA', style0)
        ws.write(0, 7, 'SUBTOTAL', style0)
        ws.write(0, 8, 'IGV', style0)
        ws.write(0, 9, 'INAFECTA', style0)
        ws.write(0, 10, 'EXONERADO', style0)
        ws.write(0, 11, 'EXPO', style0)
        ws.write(0, 12, 'PERC', style0)      
        ws.write(0, 13, 'TOTAL', style0)
        ws.write(0, 14, 'T/C', style0)
        ws.write(0, 15, 'TIPO DOC REF', style0)
        ws.write(0, 16, 'FECHA EMI REF', style0)
        ws.write(0, 17, 'SERIE REF', style0)
        ws.write(0, 18, 'NUMERO REF', style0)
        

       

        i=1

        

        self.env.cr.execute((""" SELECT  fecha_emi_doc_cpe as fec_emi, b.code td, serie_doc_cpe serie, nro_doc_cpe numero, 
                            case when estatus = 1 then 'ANULADO' else case when a.ruc_cliente = '' then  a.dni_cliente else a.ruc_cliente end end ruc, 
                            case when estatus = 1 then 'ANULADO' else a.nombre_cliente end raz_social, case when tipo_moneda = 'PEN' then 'L' else 'E' end mon, 
                            case when left(tipo_afec_igv, 1) = '1' then sub_total else 0.00 end grav, 
                            case when left(tipo_afec_igv, 1) = '1' then igv else 0.00 end igv, case when left(tipo_afec_igv, 1) = '2' then sub_total else 0.00 end exo, case when left(tipo_afec_igv, 1) = '3' then sub_total else 0.00 end ina, 
                            case when left(tipo_afec_igv, 1) = '4' then sub_total else 0.00 end exp, m_percepcion, total_cpe, 0 tc, coalesce(tipodoc_afecta,'') tipodoc_afecta, coalesce(fecdoc_afecta::text,'01/01/1900')::text fecdoc_afecta, coalesce(seriedoc_afecta,'') seriedoc_afecta , coalesce(numdoc_afecta,'') numdoc_afecta
                            from vw_tbl_cab_cpe a 
                            left join pay_document b on(a.codigo = b.code)
                            where extract(year from fecha_emi_doc_cpe)::text || lpad(extract(month from fecha_emi_doc_cpe)::text,2,'0') ='%s'
                            order by fecha_emi_doc_cpe, b.code, serie, numero; """)% self.periodo_consulta)
        oconsulta = self.env.cr.fetchall()

        for item in oconsulta:
            date_object = datetime.strptime(item[0], '%Y-%m-%d')
            ws.write(i, 0, date_object, style1)
            ws.write(i, 1, item[1])
            ws.write(i, 2, item[2])
            ws.write(i, 3, item[3])
            ws.write(i, 4, item[4])
            ws.write(i, 5, item[5])
            ws.write(i, 6, item[6])
            ws.write(i, 7, item[7], style2)
            ws.write(i, 8, item[8], style2)
            ws.write(i, 9, item[9], style2)
            ws.write(i, 10, item[10], style2)
            ws.write(i, 11, item[11], style2)
            ws.write(i, 12, item[12], style2)
            ws.write(i, 13, item[13], style2)
            ws.write(i, 14, item[14], style3)
            ws.write(i, 15, item[15], style4)

            if  item[16]=='01/01/1900':
                ws.write(i, 16, item[16])

            else:
                date_object2 = datetime.strptime(item[16], '%Y-%m-%d')
                ws.write(i, 16, date_object2, style1)
            ws.write(i, 17, item[17])
            ws.write(i, 18, item[18])
            i+=1


        '''for empe in self:
            for line in empe.order_line:
                ws.write(i, 0, line.product_id.name)
                ws.write(i, 1, line.product_qty, style2)
                i+= 1

        
        ws.write(i, 1,xlwt.Formula('SUM(B5:B%s)' % i), style3)'''
        



        #ws.write(1, 0, datetime.now(), style1)
        #ws.write(2, 0, 4)
        #ws.write(2, 1, 1)
        #ws.write(2, 2, xlwt.Formula("A3+B3"))
        #ws.write(2, 3, self.partner_id.name, style0)
        #wb.save('D:/addons_local11/example.xls')
    


    #esto estamos probando a ver si sirve para que sea archivo descargable

                    
        buf=io.BytesIO()
        wb.save(buf)

        out=base64.encodestring(buf.getvalue())             
        buf.close()
        

        self.env.cr.execute((""" DELETE FROM vistaexcel_modelo"""))
        self.invalidate_cache()

        account_move = self.env['vistaexcel.modelo']
        nom_archivo = 'regventas_' + self.periodo_consulta + '.xls'
        move_vals = {
        'txt_filename': nom_archivo,
        'txt_binary': out,
        #'id_excel': self.name                          
        }
        move = account_move.create(move_vals)

        self.env.cr.execute((""" SELECT id FROM  vistaexcel_modelo where txt_filename='%s' """ % nom_archivo))                           
        id_mientras = self.env.cr.fetchall()[0][0]
        
        return{
        'view_mode': 'form',
        'res_id': id_mientras,
        'res_model': 'vistaexcel.modelo',
        'view_type': 'form',
        'type': 'ir.actions.act_window',
        'target': 'new',
        'flags': {'action_buttons': False},
        }

        
    #termina funcion que llama al reporte
class VistaExcelModel(models.Model):
    _name="vistaexcel.modelo"

    txt_filename = fields.Char()
    txt_binary = fields.Binary()
    id_excel= fields.Char()

   
    
