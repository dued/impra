# -*- coding: utf-8 -*-

from odoo import _, models, fields, api

import requests
from requests.exceptions import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
import io
from odoo.exceptions import UserError, AccessError

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import time
from datetime import datetime,timedelta 
   

class MonedaSunat(models.Model):
	_inherit='res.currency'

	#texto_prueba=fields.Text()    
    
	def get_tipo_cambio(self,anho,mes):         

		anho_n=int(anho)
		mes_n=int(mes)
		anho_actual=int(time.strftime('%Y'))
		mes_actual=int(time.strftime('%m'))
		dias_mes=0
		anho_anterio=""
		mes_anterior=""		

		if mes_n==1:
			anho_anterio=str(anho_n - 1)
			mes_anterior="12"
		else:
			anho_anterio=anho
			mes_anterior=str(mes_n - 1)
        

        #obtener el dia del mes        
		if anho_n==anho_actual and mes_n==mes_actual:
			dias_mes_mientra=str(fields.Date.context_today(self))			
			dias_mes_mientra2=dias_mes_mientra[8:]
			dias_mes=int(dias_mes_mientra2)
		else:
			if mes=="12":
				mes_sig="01/01/"+str(anho_n+1)
			else:
				mes_sig="01/"+str(mes_n+1)+"/"+ anho

			date_object = datetime.strptime(mes_sig, '%d/%m/%Y')
			dias = timedelta(days=1)
			fin_mes= date_object-dias      
			dias_mes=int(fin_mes.strftime('%d'))
        #termina dia mes

		try:
			tip_camb_mes_actual =self.sunat_consulta(anho,mes,dias_mes)
			#self.descripcion=str(tip_camb_mes_actual)
			if tip_camb_mes_actual['1']==0:
				tip_camb_mes_anterior =self.sunat_consulta(anho_anterio,mes_anterior,-1)
				#self.descripcion += str(tip_camb_mes_anterior)
				xdia=31
				xtc=1
				for linea in range(0,32):
					if tip_camb_mes_anterior.get('%s'% str(xdia)) and xtc==1:
						xtc=tip_camb_mes_anterior['%s'% str(xdia)]

					xdia-=1

				'''for linea in range(1,32):
					if tip_camb_mes_actual.get('%s'% str(linea)):
						if tip_camb_mes_actual['%s'% str(linea)]==0:
							tip_camb_mes_actual['%s'% str(linea)]=xtc'''



				for linea in tip_camb_mes_actual:
					if  tip_camb_mes_actual[linea]==0:
						tip_camb_mes_actual[linea]=xtc
					
	       
			return (tip_camb_mes_actual)   
		except Exception as e:
			raise UserError('Sin acceso a la página Sunat')              

        

	def sunat_consulta(self,anho,mes,dias_mes):
		data_tipo_cambio={}         

		s = requests.Session()
		url="http://www.sunat.gob.pe/cl-at-ittipcam/tcS01Alias?anho="+ anho+"&mes="+ mes
		get2=s.get(url)       

		texto_consulta=get2.text

		texto_consulta=StringIO(texto_consulta).readlines()
		temp=0;
		dia=0
		tcambio=0

		mi_venta=0
       
		for li in texto_consulta:              

			if li.find("strong") != -1:
				temp=1
				dia=li.replace("<strong>","").replace("</strong>","").strip()		

			try:
				y=float(li)
			except Exception as e:
				y=0
			    
			if y>0:                       
				mi_venta=y

			data_tipo_cambio['%s'%dia]=mi_venta

		del data_tipo_cambio['0']

		if dias_mes>0:
			tc_venta=0
			data_ordenada={}

			for recorre in range(1,dias_mes + 1):
				if data_tipo_cambio.get('%s'% recorre):
					tc_venta=data_tipo_cambio['%s'% recorre]

				data_ordenada['%s'% recorre]=tc_venta
		else:
			data_ordenada=data_tipo_cambio
        
		return (data_ordenada)
   
	def data_actualiza(self):
		data_anno=str(time.strftime('%Y'))
		data_mes=str(time.strftime('%m'))		

		if self.id == 3 and self.env.user.company_id.currency_id.id == 163:
			dato_oficial=self.get_tipo_cambio(data_anno,data_mes)
			#self.descripcion=str(dato_oficial)
			#return

			if dato_oficial:
				for line in dato_oficial:
					fecha_recorre=("%s/%s/%s")% (str(line),data_mes,data_anno)
					date_object = datetime.strptime(fecha_recorre, '%d/%m/%Y')
					date_ultimo=date_object.strftime('%Y-%m-%d')
					tc=1 if dato_oficial[line]==0 else dato_oficial[line]
					busqueda=self.env['res.currency.rate'].search([('name', '=', str(date_ultimo)), ('currency_id', '=', self.id), ('company_id','=', self.env.user.company_id.id)])
					datito =({'name': date_ultimo,
									'rate': 1/tc,
									'currency_id': self.id
								})					

					if str(busqueda.id).strip()=='False':								

						self.env['res.currency.rate'].create(datito)
					else:						
						self.env['res.currency.rate'].browse(busqueda.id).write({'rate':1/tc})						
							
			else:
				raise UserError('Sin acceso a la página Sunat')

				
		




