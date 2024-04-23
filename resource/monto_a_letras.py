dic= {
'1':'UNO ',
'1c':'UN ',
'2':'DOS ',
'3':'TRES ',
'4':'CUATRO ',
'5':'CINCO ',
'6':'SEIS ',
'7':'SIETE ',
'8':'OCHO ',
'9':'NUEVE ',
'10':'DIEZ ',
'11':'ONCE ',
'12':'DOCE ',
'13':'TRECE ',
'14':'CATORCE ',
'15':'QUINCE ',
'16':'DIECISEIS ',
'17':'DIECISIETE ',
'18':'DIECIOCHO ',
'19':'DIECINUEVE ',
'20':'VEINTE ',
'21':'VEINTIUNO ',
'21c':'VEINTIUN ',
'22':'VEINTIDOS ',
'23':'VEINTITRES ',
'24':'VEINTICUATRO ',
'25':'VEINTICINCO ',
'26':'VEINTISEIS ',
'27':'VEINTISIETE ',
'28':'VEINTIOCHO ',
'29':'VEINTINUEVE ',
'30':'TREINTA ',
'40':'CUARENTA ',
'50':'CINCUENTA ',
'60':'SESENTA ',
'70':'SETENTA ',
'80':'OCHENTA ',
'90':'NOVENTA ',
'00':'CIENTO ',
'00c':'CIEN ',
'00p':'CIENTOS ',
'00q':'QUINIENTOS ',
'00n':'NOVECIENTOS ',
}

def divide_centenas(number,nivel=1):
	cadena=str(number)
	tamano=len(cadena)

	i=tamano-1
	data=[]
	cero="0"
	finalizar=0

	for recorre in range(tamano):
		x=(cero*i)

		numero=int(cadena[recorre:recorre+1])
		numerop=str(numero)
		if i >1:
			comodin=""

			if numero==1:
				if int(cadena[1:])==0:
					comodin="c"

			elif numero==5:
				comodin="q"

			elif numero==9:
				comodin="n"
			else:
				comodin="p"

			x=x+comodin
		else:
			if numero>=3:

				x=("1"+x)
				numero=numero*int(x)
				numerop=str(numero)
			else:
				comodin=""

				if nivel==2:
					comodin='c'

				numero=int(cadena[tamano-(i+1):])

				if numero==1 or numero==21:
					numerop=str(numero)+comodin
				else:
					numerop=str(numero)

				finalizar=1

		if i==2:
			if numero==1 or numero==5 or numero==9:
				numero=0

		if numero>0:
			data.append(numerop)

		if i>1:
			data.append(x)

		i-=1

		if finalizar==1:
			break

	return data


def to_letras(number):

	num_todo ='{:,.2f}'.format(round(number,2)).split('.')
	#print (num_todo)

	num_entero = num_todo[0].split(',')
	num_entero = num_entero[::-1]  #invierte el orden de los elementos de una lista

	num_decimal = num_todo[1].split(',') #para decimales
	decimal=""
	for deci in num_decimal:
		decimal+=deci




	grupo=""
	grupo1=""
	grupo2=""
	grupo3=""

	for aa in num_entero:
		if num_entero.index(aa)==3:
			lista=divide_centenas(int(aa),2)
			for item in lista:
				if (lista.index(item)==len(lista)-2 and (item =='30' or item =='40' or item =='50' or item =='60' or item =='70' or item =='80' or item =='90')):
					grupo3+=dic[str(item)]+ "Y "
				else:
					grupo3+=dic[str(item)]

			grupo3=grupo3+"MIL "
			print (grupo3)
		elif num_entero.index(aa)==2:
			lista=divide_centenas(int(aa),2)
			for item in lista:
				if (lista.index(item)==len(lista)-2 and (item =='30' or item =='40' or item =='50' or item =='60' or item =='70' or item =='80' or item =='90')):
					grupo2+=dic[str(item)]+ "Y "
				else:
					grupo2+=dic[str(item)]
			if grupo2[0:3].strip()=="UN" and len(num_entero)<=3:
				grupo2=grupo2+"MILLON "
			else:
				grupo2=grupo2+"MILLONES "

		elif num_entero.index(aa)==1:
			lista=divide_centenas(int(aa),2)
			for item in lista:
				if (lista.index(item)==len(lista)-2 and (item =='30' or item =='40' or item =='50' or item =='60' or item =='70' or item =='80' or item =='90')):
					grupo1+=dic[str(item)]+ "Y "
				else:
					grupo1+=dic[str(item)]

			grupo1=grupo1+"MIL "

		elif num_entero.index(aa)==0:
			lista=divide_centenas(int(aa),1)
			for item in lista:
				if (lista.index(item)==len(lista)-2 and (item =='30' or item =='40' or item =='50' or item =='60' or item =='70' or item =='80' or item =='90')):
					grupo+=dic[str(item)]+ " Y "
				else:
					grupo+=dic[str(item)]

		else:
			return ("solo para 12 digitos")

	if grupo=="" and grupo1=="" and grupo2=="" and grupo3=="":
		letras= "%s/100"% decimal
	else:
		letras=grupo3+grupo2+grupo1+grupo+"CON "+ "%s/100"% decimal
	return (letras)



#print (to_letras(1.05))
#print (divide_centenas(521,2))






















