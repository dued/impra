import psycopg2

# Postgres
PSQL_HOST = "5.189.154.127"
PSQL_PORT = "5432"
PSQL_USER = "openpg"
PSQL_PASS = "openpgpwd"
PSQL_DB   = "rucdni"

try:
	# Conectarse a la base de datos
	connstr = "host=%s port=%s user=%s password=%s dbname=%s" % (PSQL_HOST, PSQL_PORT, PSQL_USER, PSQL_PASS, PSQL_DB)
	conn = psycopg2.connect(connstr)

	# Abrir un cursor para realizar operaciones sobre la base de datos
	cur = conn.cursor()

	# Ejecutar una consulta SELECT
	dni = '20553840024'
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
	lt = row[10]
	mz = row[12]

	direc = ""

	if mz:
		direc = "MZ " + mz
	if lt:
		direc = direc + " LT " + lt
	if cod_zna:
		direc = direc + " " + cod_zna
	if nom_zna:
		direc = direc + " " + nom_zna

	# Hacer algo con los datos
	print(raz_social)
	print(ubigeo)
	print(tip_via)
	print(nom_via)
	print(cod_zna)
	print(nom_zna)
	print(lt)
	print(mz)
	print(direc)

except:
	print("Error de base de datos")