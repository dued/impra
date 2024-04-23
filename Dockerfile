FROM odoo:11

# Etapa 2: Instalar dependencias adicionales
USER root

RUN apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip \
    && pip3 install openpyxl==2.5.7 pytesseract qrcode pytesseract==0.1.7  phonenumbers &&\
    /bin/bash -c "rm -rf /usr/lib/python3/dist-packages/odoo/addons/point_of_sale" &&\
    /bin/bash -c "rm -rf /usr/lib/python3/dist-packages/qrcode"

# Copiando librerioa python para  prosystemperu_factura_electronica
COPY resource/monto_a_letras.py /usr/lib/python3/dist-packages/monto_a_letras.py
COPY resource/qrcode /usr/lib/python3/dist-packages/qrcode
COPY resource/point_of_sale /usr/lib/python3/dist-packages/odoo/addons/point_of_sale
COPY resource/pytesseract /usr/lib/python3/dist-packages/pytesseract
# COPY resource/run.sh /

# Cambiar de nuevo al usuario Odoo
USER odoo

# CMD [ "/run.sh" ]

# ENTRYPOINT [ "/run.sh" ]