# -*- encoding: utf-8 -*-
##############################################################################
#
#    Alexader Cuellar Morales
##############################################################################
try:
    import Image
except ImportError:
    from PIL import Image
    
try:
    from pytesseract import image_to_string
except ImportError:
    from pytesseract.pytesseract import image_to_string
    
import requests
from requests.exceptions import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
#from urllib.request import urlopen
import io

from bs4 import BeautifulSoup
from odoo import _, models, fields, api
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
from odoo.osv import osv




try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

#importacion adicional para el dni
import psycopg2
from lxml import etree
import logging
_logger = logging.getLogger(__name__)


class res_partner(models.Model):
    _inherit = 'res.partner'

    '''def _default_country(self):
        model= self.env['res.country']
        registro=model.search([('name','=', 'Peru')], limit=1)
        
        mis_id=registro.id
        
        return mis_id   '''
    
    #country_id = fields.Many2one('res.country', ondelete='restrict', default = 173)

    vat = fields.Char(store=True)
    
    
    tipo_documento=fields.Selection([('6', 'R.U.C.'),('1', 'D.N.I'),('4', 'Carnet de extranjeria'),('7', 'Pasaporte'),('A', 'Cedula diplomatica de identidad'),('0', 'Otro')], required=True ,default='6')
    vat_mio=fields.Char(placeholder="Documento", string="documento")

    vat2_mio=fields.Char(placeholder="Documento", string="documento")
    condicion=fields.Boolean(default=True)
    estado_ruc=fields.Selection([('bien', 'CONSULTA NORMAL'),('mal', 'PROBLEMAS CONSULTANDO')], default='bien',help="Seleccione deacuerdo a sus opciones")

    provincia_id = fields.Many2one('res.provincia')
    distrito_id = fields.Many2one('res.distrito')
    nombre_comercial = fields.Char()

    urbanizacion = fields.Char()

    city = fields.Char(compute='cambio_provincia',store=True)
    street2 = fields.Char(compute='cambio_distrito',store=True)

    def valida_ruc(self,ruc):
        aRuc = [[],[5,4,3,2,7,6,5,4,3,2,0],[]]
        
        for i in ruc:
            aRuc[0].append(int(i))
        
        nTot11 = 0
        for i in range(10):
            aRuc[2].append(aRuc[0][i] * aRuc[1][i])
            nTot11 += aRuc[2][i]

        aRuc[2].append(nTot11)  
        
        lnResiduo = aRuc[2][10]%11  

        lnUltDigito = 11 - lnResiduo

        lnUltDigito = int(str(lnUltDigito)[-1:])
        
        
        if lnUltDigito == aRuc[0][10]:
            return True
        else:
            return False

    @api.multi
    @api.depends('name', 'vat')
    def name_get(self):
        result = []
        for partner in self:
            name = str(partner.name) + ' - ' + str(partner.vat)
            result.append((partner.id, name))
        return result


    

    def _dni_captcha(self):       
        
        res_dni={}

        for i in range(10):


            s = requests.Session()
            
            
            try:
                r = s.get('https://cel.reniec.gob.pe/valreg/codigo.do')
            except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                if self.estado_ruc=='bien' :
                    self.condicion = False
                    ca= self.vat_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   

                    self.vat2_mio  = va

                    warning = {'title': "Error!",'message': "Verifique su Conexion a internet"}                                              
                    return {'value': res_dni, 'warning': warning }
                else:
                    self.vat2_mio = self.vat_mio
                    return 

            img=Image.open(io.BytesIO(r.content))

            img = img.convert("RGBA")
            pixdata = img.load()
            for y in xrange(img.size[1]):
                for x in xrange(img.size[0]):
                    red, green, blue, alpha=pixdata[x, y]
                    if blue<100:
                        pixdata[x, y] = (255, 255, 255, 255)



            temp_captcha_val=image_to_string(img)
            temp_captcha_val=temp_captcha_val.strip().upper()


            captcha_val=''
            for i in range(len(temp_captcha_val)):
                if temp_captcha_val[i].isalpha() or temp_captcha_val[i].isdigit():
                    captcha_val=captcha_val+temp_captcha_val[i]

            


            consuta= captcha_val.upper()
            if not consuta:
                warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                return {'value': res_dni, 'warning': warning }
            if len(captcha_val)==4 and captcha_val.isalnum():
                break

        
        #payload={'accion': 'buscar', 'nuDni': str(self.dni_mio), 'imagen': str(captcha_val)}
        try:
            #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do", params=payload)
            #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni={0}&imagen={1}", str(self.dni_mio), str(captcha_val))
            post = s.get("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni="+str(self.vat_mio)+"&imagen="+str(captcha_val))
        except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
            if self.estado_ruc=='bien' :
                self.condicion = False
                ca= self.vat_mio
                gu=len(ca)
                va=ca[0:gu-1]                   

                self.vat2_mio  = va

                warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}                                              
                return {'value': res_dni, 'warning': warning }
            else:
                self.vat2_mio = self.vat_mio
                return
        
        
        #post = consuta.post("https://cel.reniec.gob.pe/valreg/valreg.do")
        texto_consulta=post.text                         
        

        

        parser = etree.HTMLParser()
        tree   = etree.parse(StringIO(texto_consulta), parser)
        name_mio=''
        for _td in tree.findall("//td[@class='style2']"):
            if _td.text:
                _name_mio=_td.text.split("\n")
                for i in range(len(_name_mio)):
                    _name_mio[i]=_name_mio[i].strip()
                name_mio=' '.join(_name_mio)
                break

        name_mio=name_mio.strip()

        if name_mio=='Ingrese el código que aparece en la imagen':
            if self.estado_ruc=='bien' :
                self.condicion = False

                self.name=''

                ca= self.vat_mio
                gu=len(ca)
                va=ca[0:gu-1]                   

                self.vat2_mio  = va
                warning = {'title': "Error!",'message': "Por Favor, Problema al consultar,Consulte nuevamente"}
                return {'value': res_dni, 'warning': warning }
            else:
                self.vat2_mio = self.vat_mio
                return

        elif name_mio=='El DNI N°':
            if self.estado_ruc=='bien' :

                self.name=''

                self.condicion = False
                ca= self.vat_mio
                gu=len(ca)
                va=ca[0:gu-1]                   

                self.vat2_mio  = va
                warning = {'title': "Advertencia!",'message': "Por Favor, DNI Cancelado o no existe,Consulte nuevamente"}
                return {'value': res_dni, 'warning': warning }
            else:
                self.vat2_mio = self.vat2_mio

        else:
                
            self.name=name_mio

    def _dni_captcha2(self):

       
        

        res_dni={}

        for i in range(10):

            

            s = requests.Session()

            
            

            try:
                r = s.get('https://cel.reniec.gob.pe/valreg/codigo.do')
            except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                if self.estado_ruc=='bien' :
                    self.condicion = True
                    ca= self.vat2_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   

                    self.vat_mio  = va

                    warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}                                              
                    return {'value': res_dni, 'warning': warning }
                else:
                    self.vat_mio = self.vat2_mio
                    return

            img=Image.open(io.BytesIO(r.content))

            img = img.convert("RGBA")
            pixdata = img.load()
            for y in xrange(img.size[1]):
                for x in xrange(img.size[0]):
                    red, green, blue, alpha=pixdata[x, y]
                    if blue<100:
                        pixdata[x, y] = (255, 255, 255, 255)



            temp_captcha_val=image_to_string(img)
            temp_captcha_val=temp_captcha_val.strip().upper()


            captcha_val=''
            for i in range(len(temp_captcha_val)):
                if temp_captcha_val[i].isalpha() or temp_captcha_val[i].isdigit():
                    captcha_val=captcha_val+temp_captcha_val[i]

            


            consuta= captcha_val.upper()
            if not consuta:
                warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                return {'value': res_dni, 'warning': warning }
            if len(captcha_val)==4 and captcha_val.isalnum():
                break


        
        #payload={'accion': 'buscar', 'nuDni': str(self.dni_mio), 'imagen': str(captcha_val)}
        try:
            #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do", params=payload)
            #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni={0}&imagen={1}", str(self.dni_mio), str(captcha_val))
            post = s.get("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni="+str(self.vat2_mio)+"&imagen="+str(captcha_val))
        except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
            if self.estado_ruc=='bien' :
                self.condicion = True
                ca= self.vat2_mio
                gu=len(ca)
                va=ca[0:gu-1]                   

                self.vat_mio  = va
                warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}
                return {'value': res_dni, 'warning': warning }
                
            else:
                self.vat_mio = self.vat2_mio
                return
        
        
        #post = consuta.post("https://cel.reniec.gob.pe/valreg/valreg.do")
        texto_consulta=post.text                        
        

        

        parser = etree.HTMLParser()
        tree   = etree.parse(StringIO(texto_consulta), parser)
        name_mio=''
        for _td in tree.findall("//td[@class='style2']"):
            if _td.text:
                _name_mio=_td.text.split("\n")
                for i in range(len(_name_mio)):
                    _name_mio[i]=_name_mio[i].strip()
                name_mio=' '.join(_name_mio)
                break


        name_mio=name_mio.strip()
        if name_mio=='Ingrese el código que aparece en la imagen':
            if self.estado_ruc=='bien' :

                self.name=''
                
                self.condicion = True
                ca= self.vat2_mio
                gu=len(ca)
                va=ca[0:gu-1]                   

                self.vat_mio  = va
                warning = {'title': "Error!",'message': "Por Favor, Problema al consultar,Consulte nuevamente"}
                return {'value': res_dni, 'warning': warning }
            else:
                self.vat_mio = self.vat2_mio
                return
        elif name_mio=='El DNI N°':
            if self.estado_ruc=='bien' :

                self.name=''

                self.condicion = True
                ca= self.vat2_mio
                gu=len(ca)
                va=ca[0:gu-1]                   
                self.vat_mio  = va
                warning = {'title': "Advertencia!",'message': "Por Favor, DNI Cancelado o no existe,Consulte nuevamente"}
                return {'value': res_dni, 'warning': warning }
            else:
                self.vat_mio = self.vat2_mio

        else:       

            self.name=name_mio

    @api.onchange('tipo_documento','vat')
    def _get_ruc_dni(self):
        if not self.vat:
            return

        if not self.tipo_documento:
            return         

        param = [self.tipo_documento, self.vat]
        data = self.consultar_rucdni_bd(param)

        if data.get('name'):
            self.name = data['name']
            self.nombre_comercial = data['nombre_comercial']
            self.country_id = data['country_id']
            self.state_id = data['state_id']
            self.provincia_id = data['provincia_id']
            self.distrito_id = data['distrito_id']
            self.street = data['street']
            self.urbanizacion = data['urbanizacion']

        return data

    @api.model
    def consultar_rucdni_bd(self, parametros):

        data = {}

        data['name'] = ""
        data['nombre_comercial'] = ""
        data['country_id'] = False
        data['state_id'] = False
        data['provincia_id'] = False
        data['distrito_id'] = False
        data['street'] = ""
        data['urbanizacion'] = ""

        if not parametros[1]:
            return data
        if parametros[0] == '6' and len(parametros[1]) != 11:
            return data
        if parametros[0] == '1' and len(parametros[1]) != 8:
            return data

        if parametros[0] not in ('6','1'):
            return data

        if parametros[0] == '6' and len(parametros[1]) == 11:
            if self.valida_ruc(parametros[1]) == False:
                warning = {'title': "Advertencia!",'message': "RUC no valido, consulte nuevamente"}                                              
                return {'value': data, 'warning': warning }
                #raise ValidationError(_('RUC no valido'))


        # Postgres
        PSQL_HOST = "5.189.154.127"
        PSQL_PORT = "5432"
        PSQL_USER = "openpg"
        PSQL_PASS = "openpgpwd"
        PSQL_DB   = "rucdni"

        res={}

        try:
            # Conectarse a la base de datos
            connstr = "host=%s port=%s user=%s password=%s dbname=%s" % (PSQL_HOST, PSQL_PORT, PSQL_USER, PSQL_PASS, PSQL_DB)
            conn = psycopg2.connect(connstr)

            # Abrir un cursor para realizar operaciones sobre la base de datos
            cur = conn.cursor()

            # Ejecutar una consulta SELECT
            dni = parametros[1]
            sql = """
                    select * from consultar_rucdni('%s') 
                      as (raz_social varchar, estado varchar, condicion varchar, ubigeo varchar, tip_via varchar, nom_via varchar, cod_zona varchar, 
                        nom_zona varchar, numero varchar, interior varchar, lote varchar, departamento varchar, manzana varchar, kilometro varchar);
                    """ % (dni)
            cur.execute(sql)

            # Obtener los resultados como objetos Python
            row = cur.fetchone()

            # Cerrar la conexión con la base de datos
            cur.close()
            conn.close()

            # Recuperar datos del objeto Python
            raz_social = row[0]
            ubigeo = row[3]
            tip_via = row[4]
            nom_via = row[5]
            cod_zna = row[6]
            nom_zna = row[7]
            numero = row[8]
            interior = row[9]
            lt = row[10]
            dpto = row[11]
            mz = row[12]
            km = row[13]

            direc = ""

            if tip_via != "-":
                direc = tip_via + " "
            if nom_via != "-":
                direc = direc + nom_via + " "
            if km != "-":
                direc = direc + "KM. " + km + " "
            if numero != "-":
                direc = direc + "NRO. " + numero + " "
            if dpto != "-":
                direc = direc + "DPTO. " + dpto + " "
            if mz != "-":
                direc = direc + "MZA. " + mz + " "
            if lt != "-":
                direc = direc + "LOTE. " + lt + " "
            if interior != "-":
                direc = direc + "INT. " + interior + " "
            if cod_zna != "-":
                direc = direc + " " + cod_zna
            if nom_zna != "-":
                direc = direc + " " + nom_zna

            # Conmsultar IDs (UBIGEO)
            self.env.cr.execute("""SELECT d.id d_id, p.id p_id, s.id s_id, country_id
            from res_distrito d
                left join res_provincia p on(p.id = d.provincia_id)
                left join res_country_state s on(s.id = p.departamento_id)
            where d.code = '%s' """% (ubigeo))

            ubigeo_ids = self.env.cr.fetchall()

            # Hacer algo con los datos
            data['name'] = raz_social
            data['nombre_comercial'] = ""
            data['country_id'] = ubigeo_ids[0][3]
            data['state_id'] = ubigeo_ids[0][2]
            data['provincia_id'] = ubigeo_ids[0][1]
            data['distrito_id'] = ubigeo_ids[0][0]
            data['street'] = direc



            if cod_zna[0:3] == 'URB':
                data['urbanizacion'] = nom_zna

        except:
            warning = {'title': "Advertencia!",'message': "No fue posible consultar el RUC, consulte nuevamente"}                                              
            return {'value': res, 'warning': warning }

        return data


    def actualiza_ubigeo(self):
        param = [self.tipo_documento, self.vat_mio]
        data = self.consultar_rucdni_bd(param)

        if data.get('name'):
            datos = {'name' : data['name'],
            'nombre_comercial' : data['nombre_comercial'],
            'country_id' : data['country_id'],
            'state_id' : data['state_id'],
            'provincia_id' : data['provincia_id'],
            'distrito_id' : data['distrito_id'],
            'street' : data['street'],
            'urbanizacion' : data['urbanizacion']}

            self.write(datos)

    @api.model
    def consulta_rucdni(self, parametros):
        for line in self:

            data = {}

            data['name'] = ""
            data['nombre_comercial'] = ""
            data['country_id'] = False
            data['state_id'] = False
            data['provincia_id'] = False
            data['distrito_id'] = False
            data['street'] = ""
            data['urbanizacion'] = ""
            
            #if not args[1]:
            #    return data

            #_logger.info("RUC_DNI" + str(parametros))
            #_logger.info("TDOC " + parametros[0])
            #_logger.info("RUC " + parametros[1])

            xRuc = parametros[1]

            if len(parametros[1])==11 and parametros[0] == '6':

                res={}        
                                
                

                for i in range(10):

                    s = requests.Session()
                    try:                            
                        r = s.get('http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/captcha?accion=image')
                          
                    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:

                        if line.estado_ruc=='bien' :
                            line.condicion = False
                            ca= line.vat_mio
                            gu=len(ca)
                            va=ca[0:gu-1]                   

                            line.vat2_mio  = va

                            warning = {'title': "Advertencia!",'message': "No fue posible consultar el RUC, consulte nuevamente"}                                              
                            return {'value': res, 'warning': warning }
                        else:
                            line.vat2_mio = line.vat_mio
                            #data['vat2_mio'] = vat

                            
                            return data
                    
                    
                    img=Image.open(io.BytesIO(r.content))
                    captcha_val=image_to_string(img)
                    captcha_val=captcha_val.strip().upper()
                    consuta= captcha_val.upper()

                    if not consuta:
                        if line.estado_ruc=='bien' :
                            line.condicion = False
                            ca= line.vat_mio
                            gu=len(ca)
                            va=ca[0:gu-1]                   

                            line.vat2_mio  = va
                            
                            warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                            return {'value': res, 'warning': warning }
                        else:
                            #line.vat2_mio = line.vat_mio

                            return data
                        
                        
                    if captcha_val.isalpha():
                        break

                if captcha_val.isalpha() and len(captcha_val)==4:
                #get=s.get("http://www.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias?accion=consPorRuc&razSoc="+"&nroRuc="+str(line.vat)+"&nrodoc=&contexto=rrrrrrr&tQuery=on&search1="+str(line.vat)+"&codigo="+str(captcha_val)+"&tipdoc=1&search2=&coddpto=&codprov=&coddist=&search3=")
                    try:
                        get=s.get("http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias?accion=consPorRuc&nroRuc="+str(xRuc)+"&codigo="+str(captcha_val)+"&tipdoc=1")
                        
                    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError):
                        if line.estado_ruc=='bien' :
                            line.condicion = False
                            ca= line.vat_mio
                            gu=len(ca)
                            va=ca[0:gu-1]                   

                            line.vat2_mio  = va

                            warning = {'title': "Advertencia!",'message': "No fue posible Consultar el RUC,Consulte nuevamente"}                                              
                            return {'value': res, 'warning': warning }                        
                            
                        else:
                            line.vat2_mio = line.vat_mio

                            
                            return data
                        
                    texto_error='Debe verificar el número y volver a ingresar'
                    texto_consulta=get.text
                    

                    
                   

                    if texto_error in (texto_consulta):
                        #line.name=''
                        #line.street=''
                        #line.street2=''
                        #line.city=''
                        #line.state_id=''
                        #line.country_id=''

                        warning = {'title': "Error!",'message': "Por favor, ingrese número de RUC valido"}
                        return {'value': res, 'warning': warning }                
                    else:               
                    

                    
                        texto_consulta=StringIO(texto_consulta).readlines()                    
                        

                        temp=0;
                        tnombre=""
                        tdireccion=""

                        for li in texto_consulta:
                            if temp==1:
                                soup = BeautifulSoup(li)
                                tdireccion= soup.td.string
                                #tdireccion=tdireccion.string
                                break

                            if li.find("Domicilio Fiscal:") != -1:
                                temp=1
                        # Dirección

                        lcDirec =tdireccion.strip()


                      
                        #sino tiene direccion el ruc
                        if not lcDirec or len(lcDirec)<=3 :
                            for li in texto_consulta:
                                if li.find("desRuc") != -1:
                                    soup = BeautifulSoup(li)
                                    tnombre=soup.input['value']
                                    break
                            #line.name=tnombre
                            data['name'] = tnombre

                            
                            return data

                        #-------------------------------------------------


                        x = lcDirec
                        p=x.find("          ")   

                        lcDir = x[0:p+10]

                         # muestra direccion con departamento
                        line.env.cr.execute(""" SELECT name FROM  res_country_state """)
                        dr=line.env.cr.fetchall()
                        


                             

                        lcDepat=''
                        lcDepat2=''
                        #dr=["AMAZONAS","ANCASH","APURIMAC","AREQUIPA","AYACUCHO","CAJAMARCA","CUSCO","HUANCAVELICA","HUANUCO","ICA","JUNIN","LA LIBERTAD","LAMBAYEQUE","LIMA","LORETO","MADRE DE DIOS","MOQUEGUA","PASCO","PIURA","PUNO","SAN MARTIN","TACNA","TUMBES","UCAYALI","PROV. CONST. DEL CALLAO"]
                        for corre in dr:
                            corre=str(corre)
                            nn=corre.rfind("'")
                            i=corre[2:nn]

                            if lcDir.find(' '+ i + '          ')!=-1:
                                lcDepat2=i

                                #line.env.cr.execute((""" SELECT id FROM  res_country_state where name= '%s' """) % lcDepat2)                           
                                #lcDepat=line.env.cr.fetchall()[0][0]

                                posicion=lcDir.find(' '+ i + '          ')

                                lcDireccion=lcDir[0:posicion]
                                lcDireccion=lcDireccion.strip()                       
                                break

                        ubi=x[p+1:]
                        ubi=ubi.strip()

                        ubi2=ubi[1:]
                        ubi2=ubi2.strip()


                        pro=ubi2.find("-")

                        lcProv=ubi2[0:pro]
                        lcProv=lcProv.strip()   # solo muestra la provincia

                        lcDist=ubi2[pro+1:]
                        lcDist=lcDist.strip()

                        
                        # Conmsultar IDs (UBIGEO)
                        line.env.cr.execute("""SELECT d.id d_id, p.id p_id, s.id s_id, country_id
                        from res_distrito d
                            left join res_provincia p on(p.id = d.provincia_id)
                            left join res_country_state s on(s.id = p.departamento_id)
                        where d.name = '%s' and p.name = '%s' and s.name = '%s' """% (lcDist,lcProv,lcDepat2))

                        ubigeo_ids = line.env.cr.fetchall()

                        # solo muestra el distrito


                        #line.env.cr.execute(""" SELECT id FROM  res_country where name= 'Peru' """)                           
                        #line.country_id = ubigeo_ids[0][3]   
                        #line.state_id = ubigeo_ids[0][2]
                        #line.provincia_id = ubigeo_ids[0][1]
                        #line.distrito_id = ubigeo_ids[0][0]

                        urbanizacion=""
                        separador = lcDireccion.find('URB.')
                        if separador != -1:
                            
                            urbani =lcDireccion[separador+4 ::].strip()
                            sepa_urb=urbani.find('(')
                            urbanizacion = urbani[0:sepa_urb].strip()

                        #line.street=lcDireccion
                        #line.urbanizacion=urbanizacion

                        
                        tempo = 0
                        for la in texto_consulta:
                            if tempo==1:
                                soup = BeautifulSoup(la)
                                tnombre_comercial= soup.td.string                            
                                break

                            if la.find("Nombre Comercial:") != -1:
                                tempo=1

                        #line.nombre_comercial = tnombre_comercial.strip()
                        
                        

                        #line.vat2_mio = line.vat_mio
                        
                      
                        for li in texto_consulta:
                            if li.find("desRuc") != -1:
                                soup = BeautifulSoup(li)
                                tnombre=soup.input['value']

                                break
                        #line.name=tnombre

                        data['name'] = tnombre
                        data['nombre_comercial'] = tnombre_comercial.strip()
                        data['country_id'] = ubigeo_ids[0][3]
                        data['state_id'] = ubigeo_ids[0][2]
                        data['provincia_id'] = ubigeo_ids[0][1]
                        data['distrito_id'] = ubigeo_ids[0][0]
                        data['street'] = lcDireccion
                        data['urbanizacion'] = urbanizacion

                        
                        return data

                else:
                    if line.estado_ruc=='bien' :
                        line.condicion = False
                        ca= line.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        line.vat2_mio  = va
                        
                        warning = {'title': "Error!",'message': "Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }                     
                        
                    else:
                        #line.vat2_mio = line.vat_mio

                        
                        return data



            elif len(line.vat_mio)==8 and line.tipo_documento == '1':

                res_dni={}

                for i in range(10):


                    s = requests.Session()
                    
                    
                    try:
                        r = s.get('https://cel.reniec.gob.pe/valreg/codigo.do')
                    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                        if line.estado_ruc=='bien' :
                            line.condicion = False
                            ca= line.vat_mio
                            gu=len(ca)
                            va=ca[0:gu-1]                   

                            line.vat2_mio  = va

                            warning = {'title': "Error!",'message': "Verifique su Conexion a internet"}                                              
                            return {'value': res_dni, 'warning': warning }
                        else:
                            line.vat2_mio = line.vat_mio
                            return data

                    try:
                        img=Image.open(io.BytesIO(r.content))
                    except Exception as e:
                        warning = {'title': "Error!",'message': 'Servicio de Reniec no disponible...Intentelo más tarde'}                                              
                        return {'value': res_dni, 'warning': warning }
                    
                    

                    img = img.convert("RGBA")
                    pixdata = img.load()
                    for y in xrange(img.size[1]):
                        for x in xrange(img.size[0]):
                            red, green, blue, alpha=pixdata[x, y]
                            if blue<100:
                                pixdata[x, y] = (255, 255, 255, 255)



                    temp_captcha_val=image_to_string(img)
                    temp_captcha_val=temp_captcha_val.strip().upper()


                    captcha_val=''
                    for i in range(len(temp_captcha_val)):
                        if temp_captcha_val[i].isalpha() or temp_captcha_val[i].isdigit():
                            captcha_val=captcha_val+temp_captcha_val[i]

                    


                    consuta= captcha_val.upper()
                    if not consuta:
                        warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                        return {'value': res_dni, 'warning': warning }
                    if len(captcha_val)==4 and captcha_val.isalnum():
                        break

                
                #payload={'accion': 'buscar', 'nuDni': str(line.dni_mio), 'imagen': str(captcha_val)}
                try:
                    #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do", params=payload)
                    #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni={0}&imagen={1}", str(line.dni_mio), str(captcha_val))
                    post = s.get("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni="+str(line.vat_mio)+"&imagen="+str(captcha_val))
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                    if line.estado_ruc=='bien' :
                        line.condicion = False
                        ca= line.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        line.vat2_mio  = va

                        warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}                                              
                        return {'value': res_dni, 'warning': warning }
                    else:
                        line.vat2_mio = line.vat_mio
                        return data
                
                
                #post = consuta.post("https://cel.reniec.gob.pe/valreg/valreg.do")
                texto_consulta=post.text            

                parser = etree.HTMLParser()
                tree   = etree.parse(StringIO(texto_consulta), parser)
                name_mio=''
                for _td in tree.findall("//td[@class='style2']"):
                    if _td.text:
                        _name_mio=_td.text.split("\n")
                        for i in range(len(_name_mio)):
                            _name_mio[i]=_name_mio[i].strip()
                        name_mio=' '.join(_name_mio)
                        break

                name_mio=name_mio.strip()

                if name_mio=='Ingrese el código que aparece en la imagen':
                    if line.estado_ruc=='bien' :
                        line.condicion = False

                        line.name=''

                        ca= line.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        line.vat2_mio  = va
                        warning = {'title': "Error!",'message': "Por Favor, Problema al consultar,Consulte nuevamente"}
                        return {'value': res_dni, 'warning': warning }
                    else:
                        line.vat2_mio = line.vat_mio
                        return data

                elif name_mio=='El DNI N°':
                    if line.estado_ruc=='bien' :

                        line.name=''

                        line.condicion = False
                        ca= line.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        line.vat2_mio  = va
                        warning = {'title': "Advertencia!",'message': "Por Favor, DNI Cancelado o no existe,Consulte nuevamente"}
                        return {'value': res_dni, 'warning': warning }
                    else:
                        line.vat2_mio = line.vat2_mio

                else:
                        
                    line.name=name_mio            

                return data

            
            return data  

        #data['name'] = "Hola"

    @api.model
    def consulta_rucdni_pos(self, parametros):

        data = {}

        data['name'] = ""
        data['nombre_comercial'] = ""
        data['country_id'] = False
        data['state_id'] = False
        data['provincia_id'] = False
        data['distrito_id'] = False
        data['street'] = ""
        data['urbanizacion'] = ""

        xRuc = parametros[1]

        if len(parametros[1])==11 and parametros[0] == '6':

            res={}            

            for i in range(10):

                s = requests.Session()
                try:                            
                    r = s.get('http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/captcha?accion=image')
                      
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:

                    if self.estado_ruc=='bien' :
                        self.condicion = False
                        ca= self.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        self.vat2_mio  = va

                        warning = {'title': "Advertencia!",'message': "No fue posible consultar el RUC, consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }
                    else:
                        self.vat2_mio = self.vat_mio
                        
                        return data                
                
                img=Image.open(io.BytesIO(r.content))
                captcha_val=image_to_string(img)
                captcha_val=captcha_val.strip().upper()
                consuta= captcha_val.upper()

                if not consuta:
                    if self.estado_ruc=='bien' :
                        self.condicion = False
                        ca= self.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        self.vat2_mio  = va
                        
                        warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }
                    else:

                        return data
                
                if captcha_val.isalpha():
                    break

            if captcha_val.isalpha() and len(captcha_val)==4:
                try:
                    get=s.get("http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias?accion=consPorRuc&nroRuc="+str(xRuc)+"&codigo="+str(captcha_val)+"&tipdoc=1")
                    
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError):
                    if self.estado_ruc=='bien' :
                        self.condicion = False
                        ca= self.vat_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        self.vat2_mio  = va

                        warning = {'title': "Advertencia!",'message': "No fue posible Consultar el RUC,Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }                        
                        
                    else:
                        self.vat2_mio = self.vat_mio

                        return data
                    
                texto_error='Debe verificar el número y volver a ingresar'
                texto_consulta=get.text
               

                if texto_error in (texto_consulta):

                    warning = {'title': "Error!",'message': "Por favor, ingrese número de RUC valido"}
                    return {'value': res, 'warning': warning }                
                else:               
                    
                    texto_consulta=StringIO(texto_consulta).readlines()                    
                    

                    temp=0;
                    tnombre=""
                    tdireccion=""

                    for li in texto_consulta:
                        if temp==1:
                            soup = BeautifulSoup(li)
                            tdireccion= soup.td.string
                            
                            break

                        if li.find("Domicilio Fiscal:") != -1:
                            temp=1

                    lcDirec =tdireccion.strip()

                    #sino tiene direccion el ruc
                    if not lcDirec or len(lcDirec)<=3 :
                        for li in texto_consulta:
                            if li.find("desRuc") != -1:
                                soup = BeautifulSoup(li)
                                tnombre=soup.input['value']
                                break

                        data['name'] = tnombre

                        return data

                    #-------------------------------------------------
                    x = lcDirec
                    p=x.find("          ")   

                    lcDir = x[0:p+10]

                     # muestra direccion con departamento
                    self.env.cr.execute(""" SELECT name FROM  res_country_state """)
                    dr=self.env.cr.fetchall()

                    lcDepat=''
                    lcDepat2=''

                    for corre in dr:
                        corre=str(corre)
                        nn=corre.rfind("'")
                        i=corre[2:nn]

                        if lcDir.find(' '+ i + '          ')!=-1:
                            lcDepat2=i

                            posicion=lcDir.find(' '+ i + '          ')

                            lcDireccion=lcDir[0:posicion]
                            lcDireccion=lcDireccion.strip()                       
                            break

                    ubi=x[p+1:]
                    ubi=ubi.strip()

                    ubi2=ubi[1:]
                    ubi2=ubi2.strip()


                    pro=ubi2.find("-")

                    lcProv=ubi2[0:pro]
                    lcProv=lcProv.strip()   # solo muestra la provincia

                    lcDist=ubi2[pro+1:]
                    lcDist=lcDist.strip()

                    
                    # Conmsultar IDs (UBIGEO)
                    self.env.cr.execute("""SELECT d.id d_id, p.id p_id, s.id s_id, country_id
                    from res_distrito d
                        left join res_provincia p on(p.id = d.provincia_id)
                        left join res_country_state s on(s.id = p.departamento_id)
                    where d.name = '%s' and p.name = '%s' and s.name = '%s' """% (lcDist,lcProv,lcDepat2))

                    ubigeo_ids = self.env.cr.fetchall()

                    # solo muestra el distrito
                    urbanizacion=""
                    separador = lcDireccion.find('URB.')
                    if separador != -1:
                        
                        urbani =lcDireccion[separador+4 ::].strip()
                        sepa_urb=urbani.find('(')
                        urbanizacion = urbani[0:sepa_urb].strip()
                    
                    tempo = 0
                    for la in texto_consulta:
                        if tempo==1:
                            soup = BeautifulSoup(la)
                            tnombre_comercial= soup.td.string                            
                            break

                        if la.find("Nombre Comercial:") != -1:
                            tempo=1
                  
                    for li in texto_consulta:
                        if li.find("desRuc") != -1:
                            soup = BeautifulSoup(li)
                            tnombre=soup.input['value']

                            break
                    
                    data['name'] = tnombre
                    data['nombre_comercial'] = tnombre_comercial.strip()
                    data['country_id'] = ubigeo_ids[0][3]
                    data['state_id'] = ubigeo_ids[0][2]
                    data['provincia_id'] = ubigeo_ids[0][1]
                    data['distrito_id'] = ubigeo_ids[0][0]
                    data['street'] = lcDireccion
                    data['urbanizacion'] = urbanizacion

                    return data

            else:
                if self.estado_ruc=='bien' :
                    self.condicion = False
                    ca= self.vat_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   

                    self.vat2_mio  = va
                    
                    warning = {'title': "Error!",'message': "Consulte nuevamente"}                                              
                    return {'value': res, 'warning': warning }                     
                    
                else:
                    
                    return data
        
        return data

    #@api.onchange('vat2_mio')
    def _get_captcha2(self):
        if not self.vat2_mio:
            return False
        if len(self.vat2_mio)==11 and self.tipo_documento == '6':

            res={}        
                            
            

            for i in range(10):

                s = requests.Session()
                try:                            
                    r = s.get('http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/captcha?accion=image')   
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                    if self.estado_ruc=='bien':
                        self.condicion = True
                        ca= self.vat2_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                    
                        
                        self.vat_mio  = va
                                            
                        warning = {'title': "Advertencia!",'message': "No fue posible Consultar el RUC,Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }
                    else:
                        self.vat_mio = self.vat2_mio
                        return    



                img=Image.open(io.BytesIO(r.content))

                captcha_val=image_to_string(img)
                captcha_val=captcha_val.strip().upper()
                #return (s, captcha_val)         



                consuta= captcha_val.upper()
                if not consuta:
                    if self.estado_ruc=='bien':
                        self.condicion = True
                        ca= self.vat2_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                    
                        
                        self.vat_mio  = va                                          
                        warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }
                    else:
                        self.vat_mio = self.vat2_mio
                        return                    
                    #res['warning'] = {}
                    #res['warning']['title'] = _('Error de Conección')
                    #res['warning']['message'] = _('El Servidor no está disponible, Inténtalo de nuevo!')
                    
                    #return res
                if captcha_val.isalpha():
                    break

            if captcha_val.isalpha() and len(captcha_val)==4:               


            #get=s.get("http://www.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias?accion=consPorRuc&razSoc="+"&nroRuc="+str(self.vat)+"&nrodoc=&contexto=rrrrrrr&tQuery=on&search1="+str(self.vat)+"&codigo="+str(captcha_val)+"&tipdoc=1&search2=&coddpto=&codprov=&coddist=&search3=")
                try:
                    get=s.get("http://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias?accion=consPorRuc&nroRuc="+str(self.vat2_mio)+"&codigo="+str(captcha_val)+"&tipdoc=1")
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError):
                    if self.estado_ruc=='bien':
                        self.condicion = True
                        ca= self.vat2_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                    
                        
                        self.vat_mio  = va
                                            
                        warning = {'title': "Advertencia!",'message': "No fue posible Consultar el RUC,Consulte nuevamente"}                                              
                        return {'value': res, 'warning': warning }
                    else:
                        self.vat_mio = self.vat2_mio
                        return
                                    
                    #raise osv.except_osv(_('Error'), _('No fue posible Consultar el ruc,Consulte nuevamente'))                    
                    #return
                texto_error='Debe verificar el número y volver a ingresar'
                texto_consulta=get.text
                               

                if texto_error in (texto_consulta):
                    self.name=''
                    self.street=''
                    self.street2=''
                    self.city=''
                    self.state_id=''
                    self.country_id=''

                    warning = {'title': "Error!",'message': "Por favor, ingrese número de RUC valido"}
                    return {'value': res, 'warning': warning }                  
                else:

                
                

                
                    texto_consulta=StringIO(texto_consulta).readlines()
                    
                    
                    temp=0;
                    tnombre=""
                    tdireccion=""

                    for li in texto_consulta:
                        if temp==1:
                            soup = BeautifulSoup(li)
                            tdireccion= soup.td.string
                            #tdireccion=tdireccion.string
                            break

                        if li.find("Domicilio Fiscal:") != -1:
                            temp=1
                    # Dirección

                    lcDirec =tdireccion.strip()

                                        
                    #sino tiene direccion el ruc
                    if not lcDirec or len(lcDirec)<=3 :
                        for li in texto_consulta:
                            if li.find("desRuc") != -1:
                                soup = BeautifulSoup(li)
                                tnombre=soup.input['value']
                                break
                        self.name=tnombre
                        return

                    #-------------------------------------------------






                    x = lcDirec
                    p=x.find("          ")   

                    lcDir = x[0:p+10]

                     # muestra direccion con departamento
                    self.env.cr.execute(""" SELECT name FROM  res_country_state """)
                    dr=self.env.cr.fetchall()         
                         

                    lcDepat=''
                    lcDepat2=''
                    #dr=["AMAZONAS","ANCASH","APURIMAC","AREQUIPA","AYACUCHO","CAJAMARCA","CUSCO","HUANCAVELICA","HUANUCO","ICA","JUNIN","LA LIBERTAD","LAMBAYEQUE","LIMA","LORETO","MADRE DE DIOS","MOQUEGUA","PASCO","PIURA","PUNO","SAN MARTIN","TACNA","TUMBES","UCAYALI","PROV. CONST. DEL CALLAO"]
                    for corre in dr:

                        corre=str(corre)
                        nn=corre.rfind("'")
                        i=corre[2:nn]


                        if lcDir.find(' '+ i + '          ')!=-1:
                            lcDepat2=i

                           # self.env.cr.execute((""" SELECT id FROM  res_country_state where name= '%s' """) % lcDepat2)                           
                            #lcDepat=self.env.cr.fetchall()[0][0]


                            posicion=lcDir.find(' '+ i + '          ')

                            lcDireccion=lcDir[0:posicion]
                            lcDireccion=lcDireccion.strip()                       
                            break

                    ubi=x[p+1:]
                    ubi=ubi.strip()

                    ubi2=ubi[1:]
                    ubi2=ubi2.strip()


                    pro=ubi2.find("-")

                    lcProv=ubi2[0:pro]
                    lcProv=lcProv.strip()   # solo muestra la provincia

                    lcDist=ubi2[pro+1:]
                    lcDist=lcDist.strip()

                    

                    # Conmsultar IDs (UBIGEO)
                    self.env.cr.execute("""SELECT d.id d_id, p.id p_id, s.id s_id, country_id
                    from res_distrito d
                        left join res_provincia p on(p.id = d.provincia_id)
                        left join res_country_state s on(s.id = p.departamento_id)
                    where d.name = '%s' and p.name = '%s' and s.name = '%s' """% (lcDist,lcProv,lcDepat2))

                    ubigeo_ids = self.env.cr.fetchall()

                    # solo muestra el distrito


                    #self.env.cr.execute(""" SELECT id FROM  res_country where name= 'Peru' """)                           
                    self.country_id = ubigeo_ids[0][3]   
                    self.state_id = ubigeo_ids[0][2]
                    self.provincia_id = ubigeo_ids[0][1]
                    self.distrito_id = ubigeo_ids[0][0]

                    urbanizacion=""
                    separador = lcDireccion.find('URB.')
                    if separador != -1:
                        
                        urbani =lcDireccion[separador+4 ::].strip()
                        sepa_urb=urbani.find('(')
                        urbanizacion = urbani[0:sepa_urb].strip()

                    self.street=lcDireccion
                    self.urbanizacion=urbanizacion


                    tempo = 0
                    for la in texto_consulta:
                        if tempo==1:
                            soup = BeautifulSoup(la)
                            tnombre_comercial= soup.td.string                            
                            break

                        if la.find("Nombre Comercial:") != -1:
                            tempo=1

                    self.nombre_comercial = tnombre_comercial.strip()
                    

                    
                    

                    self.vat_mio=self.vat2_mio

                    
                    
                  
                    for li in texto_consulta:
                        if li.find("desRuc") != -1:
                            soup = BeautifulSoup(li)
                            tnombre=soup.input['value']

                            break
                    self.name=tnombre
            else:
                if self.estado_ruc=='bien':
                    self.condicion = True
                    ca= self.vat2_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                    
                    
                    self.vat_mio  = va                                       
                    warning = {'title': "Error!",'message': "Consulte nuevamente"}                                              
                    return {'value': res, 'warning': warning }
                else:
                    self.vat_mio = self.vat2_mio
                    return                
                #raise osv.except_osv(_('Error'), _('Consulte nuevamente'))
                #return

        elif len(self.vat2_mio)==8 and self.tipo_documento == '1':





            res_dni={}

            for i in range(10):

                

                s = requests.Session()

                
                

                try:
                    r = s.get('https://cel.reniec.gob.pe/valreg/codigo.do')
                except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                    if self.estado_ruc=='bien' :
                        self.condicion = True
                        ca= self.vat2_mio
                        gu=len(ca)
                        va=ca[0:gu-1]                   

                        self.vat_mio  = va

                        warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}                                              
                        return {'value': res_dni, 'warning': warning }
                    else:
                        self.vat_mio = self.vat2_mio
                        return

                img=Image.open(io.BytesIO(r.content))

                img = img.convert("RGBA")
                pixdata = img.load()
                for y in xrange(img.size[1]):
                    for x in xrange(img.size[0]):
                        red, green, blue, alpha=pixdata[x, y]
                        if blue<100:
                            pixdata[x, y] = (255, 255, 255, 255)



                temp_captcha_val=image_to_string(img)
                temp_captcha_val=temp_captcha_val.strip().upper()


                captcha_val=''
                for i in range(len(temp_captcha_val)):
                    if temp_captcha_val[i].isalpha() or temp_captcha_val[i].isdigit():
                        captcha_val=captcha_val+temp_captcha_val[i]

                


                consuta= captcha_val.upper()
                if not consuta:
                    warning = {'title': "Advertencia!",'message': "Servidor no está disponible,Consulte nuevamente"}                                              
                    return {'value': res_dni, 'warning': warning }
                if len(captcha_val)==4 and captcha_val.isalnum():
                    break


            
            #payload={'accion': 'buscar', 'nuDni': str(self.dni_mio), 'imagen': str(captcha_val)}
            try:
                #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do", params=payload)
                #post = s.post("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni={0}&imagen={1}", str(self.dni_mio), str(captcha_val))
                post = s.get("https://cel.reniec.gob.pe/valreg/valreg.do?accion=buscar&nuDni="+str(self.vat2_mio)+"&imagen="+str(captcha_val))
            except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as mensa:
                if self.estado_ruc=='bien' :
                    self.condicion = True
                    ca= self.vat2_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   

                    self.vat_mio  = va
                    warning = {'title': "Error!",'message': "Sin Acceso a Internet,Verifique su Conexion a internet"}
                    return {'value': res_dni, 'warning': warning }
                    
                else:
                    self.vat_mio = self.vat2_mio
                    return
            
            
            #post = consuta.post("https://cel.reniec.gob.pe/valreg/valreg.do")
            texto_consulta=post.text                        
            

            

            parser = etree.HTMLParser()
            tree   = etree.parse(StringIO(texto_consulta), parser)
            name_mio=''
            for _td in tree.findall("//td[@class='style2']"):
                if _td.text:
                    _name_mio=_td.text.split("\n")
                    for i in range(len(_name_mio)):
                        _name_mio[i]=_name_mio[i].strip()
                    name_mio=' '.join(_name_mio)
                    break


            name_mio=name_mio.strip()
            if name_mio=='Ingrese el código que aparece en la imagen':
                if self.estado_ruc=='bien' :

                    self.name=''
                    
                    self.condicion = True
                    ca= self.vat2_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   

                    self.vat_mio  = va
                    warning = {'title': "Error!",'message': "Por Favor, Problema al consultar,Consulte nuevamente"}
                    return {'value': res_dni, 'warning': warning }
                else:
                    self.vat_mio = self.vat2_mio
                    return
            elif name_mio=='El DNI N°':
                if self.estado_ruc=='bien' :

                    self.name=''

                    self.condicion = True
                    ca= self.vat2_mio
                    gu=len(ca)
                    va=ca[0:gu-1]                   
                    self.vat_mio  = va
                    warning = {'title': "Advertencia!",'message': "Por Favor, DNI Cancelado o no existe,Consulte nuevamente"}
                    return {'value': res_dni, 'warning': warning }
                else:
                    self.vat_mio = self.vat2_mio

            else:       

                self.name=name_mio

    @api.onchange('tipo_documento')
    def _cambio_tipo(self):
       
        self.street=''
        self.street2=''
        self.city=''
        self.state_id = False
        self.country_id = False
        self.provincia_id = False
        self.distrito_id = False
        self.urbanizacion = ''
        self.nombre_comercial = ''
        self.vat_mio=''
        self.vat2_mio=''

    @api.one            
    @api.depends('provincia_id')
    def cambio_provincia(self):
        if not self.provincia_id:
            return
        
        self.city=self.provincia_id.name

    @api.one
    @api.depends('distrito_id')
    def cambio_distrito(self):        
        if not self.distrito_id:
            return

        self.street2= self.distrito_id.name

    @api.constrains('vat','tipo_documento')
    def _restringuiendo_ruc_dni(self):
        if self.parent_id:
            return
        if self.is_company == False:
            return

        if not self.vat:
            raise ValidationError(_('Ingrese número de DNI,RUC,Otros,etc segun el tipo de documento'))
        
        for data in self:
            if data.tipo_documento=='1' and len(data.vat) != 8:
                raise ValidationError(_('El número de DNI debe tener 8 digitos'))
            
            if data.tipo_documento=='6' and len(data.vat) != 11:
                raise ValidationError(_('El número de RUC debe tener 11 digitos'))
            
