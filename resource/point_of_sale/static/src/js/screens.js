odoo.define('point_of_sale.screens', function (require) {
"use strict";
// This file contains the Screens definitions. Screens are the
// content of the right pane of the pos, containing the main functionalities. 
//
// Screens must be defined and named in chrome.js before use.
//
// Screens transitions are controlled by the Gui.
//  gui.set_startup_screen() sets the screen displayed at startup
//  gui.set_default_screen() sets the screen displayed for new orders
//  gui.show_screen() shows a screen
//  gui.back() goes to the previous screen
//
// Screen state is saved in the order. When a new order is selected,
// a screen is displayed based on the state previously saved in the order.
// this is also done in the Gui with:
//  gui.show_saved_screen()
//
// All screens inherit from ScreenWidget. The only addition from the base widgets
// are show() and hide() which shows and hides the screen but are also used to 
// bind and unbind actions on widgets and devices. The gui guarantees
// that only one screen is shown at the same time and that show() is called after all
// hide()s
//
// Each Screens must be independant from each other, and should have no 
// persistent state outside the models. Screen state variables are reset at
// each screen display. A screen can be called with parameters, which are
// to be used for the duration of the screen only. 

var PosBaseWidget = require('point_of_sale.BaseWidget');
var gui = require('point_of_sale.gui');
var models = require('point_of_sale.models');
var core = require('web.core');
var rpc = require('web.rpc');
var utils = require('web.utils');
var field_utils = require('web.field_utils');

var QWeb = core.qweb;
var _t = core._t;

var round_pr = utils.round_precision;
var invoice_id = 0;

/*--------------------------------------*\
 |          THE SCREEN WIDGET           |
\*======================================*/

// The screen widget is the base class inherited
// by all screens.
var ScreenWidget = PosBaseWidget.extend({

    init: function(parent,options){
        this._super(parent,options);
        this.hidden = false;
    },

    barcode_product_screen:         'products',     //if defined, this screen will be loaded when a product is scanned

    // what happens when a product is scanned : 
    // it will add the product to the order and go to barcode_product_screen. 
    barcode_product_action: function(code){
        var self = this;
        if (self.pos.scan_product(code)) {
            if (self.barcode_product_screen) {
                self.gui.show_screen(self.barcode_product_screen, null, null, true);
            }
        } else {
            this.barcode_error_action(code);
        }
    },

    // what happens when a cashier id barcode is scanned.
    // the default behavior is the following : 
    // - if there's a user with a matching barcode, put it as the active 'cashier', go to cashier mode, and return true
    // - else : do nothing and return false. You probably want to extend this to show and appropriate error popup... 
    barcode_cashier_action: function(code){
        var self = this;
        var users = this.pos.users;
        for(var i = 0, len = users.length; i < len; i++){
            if(users[i].barcode === code.code){
                if (users[i].id !== this.pos.get_cashier().id && users[i].pos_security_pin) {
                    return this.gui.ask_password(users[i].pos_security_pin).then(function(){
                        self.pos.set_cashier(users[i]);
                        self.chrome.widget.username.renderElement();
                        return true;
                    });
                } else {
                    this.pos.set_cashier(users[i]);
                    this.chrome.widget.username.renderElement();
                    return true;
                }
            }
        }
        this.barcode_error_action(code);
        return false;
    },
    
    // what happens when a client id barcode is scanned.
    // the default behavior is the following : 
    // - if there's a user with a matching barcode, put it as the active 'client' and return true
    // - else : return false. 
    barcode_client_action: function(code){
        var partner = this.pos.db.get_partner_by_barcode(code.code);
        if(partner){
            this.pos.get_order().set_client(partner);
            return true;
        }
        this.barcode_error_action(code);
        return false;
    },
    
    // what happens when a discount barcode is scanned : the default behavior
    // is to set the discount on the last order.
    barcode_discount_action: function(code){
        var last_orderline = this.pos.get_order().get_last_orderline();
        if(last_orderline){
            last_orderline.set_discount(code.value);
        }
    },
    // What happens when an invalid barcode is scanned : shows an error popup.
    barcode_error_action: function(code) {
        var show_code;
        if (code.code.length > 32) {
            show_code = code.code.substring(0,29)+'...';
        } else {
            show_code = code.code;
        }
        this.gui.show_popup('error-barcode',show_code);
    },

    // this method shows the screen and sets up all the widget related to this screen. Extend this method
    // if you want to alter the behavior of the screen.
    show: function(){
        var self = this;

        this.hidden = false;
        if(this.$el){
            this.$el.removeClass('oe_hidden');
        }

        this.pos.barcode_reader.set_action_callback({
            'cashier': _.bind(self.barcode_cashier_action, self),
            'product': _.bind(self.barcode_product_action, self),
            'weight': _.bind(self.barcode_product_action, self),
            'price': _.bind(self.barcode_product_action, self),
            'client' : _.bind(self.barcode_client_action, self),
            'discount': _.bind(self.barcode_discount_action, self),
            'error'   : _.bind(self.barcode_error_action, self),
        });
    },

    // this method is called when the screen is closed to make place for a new screen. this is a good place
    // to put your cleanup stuff as it is guaranteed that for each show() there is one and only one close()
    close: function(){
        if(this.pos.barcode_reader){
            this.pos.barcode_reader.reset_action_callbacks();
        }
    },

    // this methods hides the screen. It's not a good place to put your cleanup stuff as it is called on the
    // POS initialization.
    hide: function(){
        this.hidden = true;
        if(this.$el){
            this.$el.addClass('oe_hidden');
        }
    },

    // we need this because some screens re-render themselves when they are hidden
    // (due to some events, or magic, or both...)  we must make sure they remain hidden.
    // the good solution would probably be to make them not re-render themselves when they
    // are hidden. 
    renderElement: function(){
        this._super();
        if(this.hidden){
            if(this.$el){
                this.$el.addClass('oe_hidden');
            }
        }
    },
});

/*--------------------------------------*\
 |          THE DOM CACHE               |
\*======================================*/

// The Dom Cache is used by various screens to improve
// their performances when displaying many time the 
// same piece of DOM.
//
// It is a simple map from string 'keys' to DOM Nodes.
//
// The cache empties itself based on usage frequency 
// stats, so you may not always get back what
// you put in.

var DomCache = core.Class.extend({
    init: function(options){
        options = options || {};
        this.max_size = options.max_size || 2000;

        this.cache = {};
        this.access_time = {};
        this.size = 0;
    },
    cache_node: function(key,node){
        var cached = this.cache[key];
        this.cache[key] = node;
        this.access_time[key] = new Date().getTime();
        if(!cached){
            this.size++;
            while(this.size >= this.max_size){
                var oldest_key = null;
                var oldest_time = new Date().getTime();
                for(key in this.cache){
                    var time = this.access_time[key];
                    if(time <= oldest_time){
                        oldest_time = time;
                        oldest_key  = key;
                    }
                }
                if(oldest_key){
                    delete this.cache[oldest_key];
                    delete this.access_time[oldest_key];
                }
                this.size--;
            }
        }
        return node;
    },
    clear_node: function(key) {
        var cached = this.cache[key];
        if (cached) {
            delete this.cache[key];
            delete this.access_time[key];
            this.size --;
        }
    },
    get_node: function(key){
        var cached = this.cache[key];
        if(cached){
            this.access_time[key] = new Date().getTime();
        }
        return cached;
    },
});

/*--------------------------------------*\
 |          THE SCALE SCREEN            |
\*======================================*/

// The scale screen displays the weight of
// a product on the electronic scale.

var ScaleScreenWidget = ScreenWidget.extend({
    template:'ScaleScreenWidget',

    next_screen: 'products',
    previous_screen: 'products',

    show: function(){
        this._super();
        var self = this;
        var queue = this.pos.proxy_queue;

        this.set_weight(0);
        this.renderElement();

        this.hotkey_handler = function(event){
            if(event.which === 13){
                self.order_product();
                self.gui.show_screen(self.next_screen);
            }else if(event.which === 27){
                self.gui.show_screen(self.previous_screen);
            }
        };

        $('body').on('keypress',this.hotkey_handler);

        this.$('.back').click(function(){
            self.gui.show_screen(self.previous_screen);
        });

        this.$('.next,.buy-product').click(function(){
            self.gui.show_screen(self.next_screen);
            // add product *after* switching screen to scroll properly
            self.order_product();
        });

        queue.schedule(function(){
            return self.pos.proxy.scale_read().then(function(weight){
                self.set_weight(weight.weight);
            });
        },{duration:500, repeat: true});

    },
    get_product: function(){
        return this.gui.get_current_screen_param('product');
    },
    _get_active_pricelist: function(){
        var current_order = this.pos.get_order();
        var current_pricelist = this.pos.default_pricelist;

        if (current_order) {
            current_pricelist = current_order.pricelist;
        }

        return current_pricelist;
    },
    order_product: function(){
        this.pos.get_order().add_product(this.get_product(),{ quantity: this.weight });
    },
    get_product_name: function(){
        var product = this.get_product();
        return (product ? product.display_name : undefined) || 'Unnamed Product';
    },
    get_product_price: function(){
        var product = this.get_product();
        var pricelist = this._get_active_pricelist();
        return (product ? product.get_price(pricelist, this.weight) : 0) || 0;
    },
    get_product_uom: function(){
        var product = this.get_product();

        if(product){
            return this.pos.units_by_id[product.uom_id[0]].name;
        }else{
            return '';
        }
    },
    set_weight: function(weight){
        this.weight = weight;
        this.$('.weight').text(this.get_product_weight_string());
        this.$('.computed-price').text(this.get_computed_price_string());
    },
    get_product_weight_string: function(){
        var product = this.get_product();
        var defaultstr = (this.weight || 0).toFixed(3) + ' Kg';
        if(!product || !this.pos){
            return defaultstr;
        }
        var unit_id = product.uom_id;
        if(!unit_id){
            return defaultstr;
        }
        var unit = this.pos.units_by_id[unit_id[0]];
        var weight = round_pr(this.weight || 0, unit.rounding);
        var weightstr = weight.toFixed(Math.ceil(Math.log(1.0/unit.rounding) / Math.log(10) ));
        weightstr += ' ' + unit.name;
        return weightstr;
    },
    get_computed_price_string: function(){
        return this.format_currency(this.get_product_price() * this.weight);
    },
    close: function(){
        this._super();
        $('body').off('keypress',this.hotkey_handler);

        this.pos.proxy_queue.clear();
    },
});
gui.define_screen({name: 'scale', widget: ScaleScreenWidget});

/*--------------------------------------*\
 |         THE PRODUCT SCREEN           |
\*======================================*/

// The product screen contains the list of products,
// The category selector and the order display.
// It is the default screen for orders and the
// startup screen for shops.
//
// There product screens uses many sub-widgets,
// the code follows.


/* ------------ The Numpad ------------ */

// The numpad that edits the order lines.

var NumpadWidget = PosBaseWidget.extend({
    template:'NumpadWidget',
    init: function(parent) {
        this._super(parent);
        this.state = new models.NumpadState();
    },
    start: function() {
        this.applyAccessRights();
        this.state.bind('change:mode', this.changedMode, this);
        this.pos.bind('change:cashier', this.applyAccessRights, this);
        this.changedMode();
        this.$el.find('.numpad-backspace').click(_.bind(this.clickDeleteLastChar, this));
        this.$el.find('.numpad-minus').click(_.bind(this.clickSwitchSign, this));
        this.$el.find('.number-char').click(_.bind(this.clickAppendNewChar, this));
        this.$el.find('.mode-button').click(_.bind(this.clickChangeMode, this));
    },
    applyAccessRights: function() {
        var has_price_control_rights = !this.pos.config.restrict_price_control || this.pos.get_cashier().role == 'manager';
        this.$el.find('.mode-button[data-mode="price"]')
            .toggleClass('disabled-mode', !has_price_control_rights)
            .prop('disabled', !has_price_control_rights);
    },
    clickDeleteLastChar: function() {
        return this.state.deleteLastChar();
    },
    clickSwitchSign: function() {
        return this.state.switchSign();
    },
    clickAppendNewChar: function(event) {
        var newChar;
        newChar = event.currentTarget.innerText || event.currentTarget.textContent;
        return this.state.appendNewChar(newChar);
    },
    clickChangeMode: function(event) {
        var newMode = event.currentTarget.attributes['data-mode'].nodeValue;
        return this.state.changeMode(newMode);
    },
    changedMode: function() {
        var mode = this.state.get('mode');
        $('.selected-mode').removeClass('selected-mode');
        $(_.str.sprintf('.mode-button[data-mode="%s"]', mode), this.$el).addClass('selected-mode');
    },
});

/* ---------- The Action Pad ---------- */

// The action pad contains the payment button and the 
// customer selection button

var ActionpadWidget = PosBaseWidget.extend({
    template: 'ActionpadWidget',
    init: function(parent, options) {
        var self = this;
        this._super(parent, options);

        this.pos.bind('change:selectedClient', function() {
            self.renderElement();
        });
    },
    renderElement: function() {
        var self = this;
        this._super();
        this.$('.pay').click(function(){
            var order = self.pos.get_order();
            var has_valid_product_lot = _.every(order.orderlines.models, function(line){
                return line.has_valid_product_lot();
            });
            if(!has_valid_product_lot){
                self.gui.show_popup('confirm',{
                    'title': _t('Empty Serial/Lot Number'),
                    'body':  _t('One or more product(s) required serial/lot number.'),
                    confirm: function(){
                        self.gui.show_screen('payment');
                    },
                });
            }else{
                self.gui.show_screen('payment');
            }
        });
        this.$('.set-customer').click(function(){
            self.gui.show_screen('clientlist');
        });
    }
});

/* --------- The Order Widget --------- */

// Displays the current Order.

var OrderWidget = PosBaseWidget.extend({
    template:'OrderWidget',
    init: function(parent, options) {
        var self = this;
        this._super(parent,options);

        this.numpad_state = options.numpad_state;
        this.numpad_state.reset();
        this.numpad_state.bind('set_value',   this.set_value, this);

        this.pos.bind('change:selectedOrder', this.change_selected_order, this);

        this.line_click_handler = function(event){
            self.click_line(this.orderline, event);
        };

        if (this.pos.get_order()) {
            this.bind_order_events();
        }

    },
    click_line: function(orderline, event) {
        this.pos.get_order().select_orderline(orderline);
        this.numpad_state.reset();
    },


    set_value: function(val) {
    	var order = this.pos.get_order();
    	if (order.get_selected_orderline()) {
            var mode = this.numpad_state.get('mode');
            if( mode === 'quantity'){
                order.get_selected_orderline().set_quantity(val);
            }else if( mode === 'discount'){
                order.get_selected_orderline().set_discount(val);
            }else if( mode === 'price'){
                var selected_orderline = order.get_selected_orderline();
                selected_orderline.price_manually_set = true;
                selected_orderline.set_unit_price(val);
            }
    	}
    },
    change_selected_order: function() {
        if (this.pos.get_order()) {
            this.bind_order_events();
            this.numpad_state.reset();
            this.renderElement();
        }
    },
    orderline_add: function(){
        this.numpad_state.reset();
        this.renderElement('and_scroll_to_bottom');
    },
    orderline_remove: function(line){
        this.remove_orderline(line);
        this.numpad_state.reset();
        this.update_summary();
    },
    orderline_change: function(line){
        this.rerender_orderline(line);
        this.update_summary();
    },
    bind_order_events: function() {
        var order = this.pos.get_order();
            order.unbind('change:client', this.update_summary, this);
            order.bind('change:client',   this.update_summary, this);
            order.unbind('change',        this.update_summary, this);
            order.bind('change',          this.update_summary, this);

        var lines = order.orderlines;
            lines.unbind('add',     this.orderline_add,    this);
            lines.bind('add',       this.orderline_add,    this);
            lines.unbind('remove',  this.orderline_remove, this);
            lines.bind('remove',    this.orderline_remove, this); 
            lines.unbind('change',  this.orderline_change, this);
            lines.bind('change',    this.orderline_change, this);

    },
    render_orderline: function(orderline){
        var el_str  = QWeb.render('Orderline',{widget:this, line:orderline}); 
        var el_node = document.createElement('div');
            el_node.innerHTML = _.str.trim(el_str);
            el_node = el_node.childNodes[0];
            el_node.orderline = orderline;
            el_node.addEventListener('click',this.line_click_handler);
        var el_lot_icon = el_node.querySelector('.line-lot-icon');
        if(el_lot_icon){
            el_lot_icon.addEventListener('click', (function() {
                this.show_product_lot(orderline);
            }.bind(this)));
        }

        orderline.node = el_node;
        return el_node;
    },
    remove_orderline: function(order_line){
        if(this.pos.get_order().get_orderlines().length === 0){
            this.renderElement();
        }else{
            order_line.node.parentNode.removeChild(order_line.node);
        }
    },
    rerender_orderline: function(order_line){
        var node = order_line.node;
        var replacement_line = this.render_orderline(order_line);
        node.parentNode.replaceChild(replacement_line,node);
    },
    // overriding the openerp framework replace method for performance reasons
    replace: function($target){
        this.renderElement();
        var target = $target[0];
        target.parentNode.replaceChild(this.el,target);
    },
    renderElement: function(scrollbottom){
        var order  = this.pos.get_order();
        if (!order) {
            return;
        }
        var orderlines = order.get_orderlines();

        var el_str  = QWeb.render('OrderWidget',{widget:this, order:order, orderlines:orderlines});

        var el_node = document.createElement('div');
            el_node.innerHTML = _.str.trim(el_str);
            el_node = el_node.childNodes[0];


        var list_container = el_node.querySelector('.orderlines');
        for(var i = 0, len = orderlines.length; i < len; i++){
            var orderline = this.render_orderline(orderlines[i]);
            list_container.appendChild(orderline);
        }

        if(this.el && this.el.parentNode){
            this.el.parentNode.replaceChild(el_node,this.el);
        }
        this.el = el_node;
        this.update_summary();

        if(scrollbottom){
            this.el.querySelector('.order-scroller').scrollTop = 100 * orderlines.length;
        }
    },
    update_summary: function(){
        var order = this.pos.get_order();
        if (!order.get_orderlines().length) {
            return;
        }

        var total     = order ? order.get_total_with_tax() : 0;
        var taxes     = order ? total - order.get_total_without_tax() : 0;

        this.el.querySelector('.summary .total > .value').textContent = this.format_currency(total);
        this.el.querySelector('.summary .total .subentry .value').textContent = this.format_currency(taxes);
    },
    show_product_lot: function(orderline){
        this.pos.get_order().select_orderline(orderline);
        var order = this.pos.get_order();
        order.display_lot_popup();
    },
});

/* ------ The Product Categories ------ */

// Display and navigate the product categories.
// Also handles searches.
//  - set_category() to change the displayed category
//  - reset_category() to go to the root category
//  - perform_search() to search for products
//  - clear_search()   does what it says.

var ProductCategoriesWidget = PosBaseWidget.extend({
    template: 'ProductCategoriesWidget',
    init: function(parent, options){
        var self = this;
        this._super(parent,options);
        this.product_type = options.product_type || 'all';  // 'all' | 'weightable'
        this.onlyWeightable = options.onlyWeightable || false;
        this.category = this.pos.root_category;
        this.breadcrumb = [];
        this.subcategories = [];
        this.product_list_widget = options.product_list_widget || null;
        this.category_cache = new DomCache();
        this.start_categ_id = this.pos.config.iface_start_categ_id ? this.pos.config.iface_start_categ_id[0] : 0;
        this.set_category(this.pos.db.get_category_by_id(this.start_categ_id));
        
        this.switch_category_handler = function(event){
            self.set_category(self.pos.db.get_category_by_id(Number(this.dataset.categoryId)));
            self.renderElement();
        };
        
        this.clear_search_handler = function(event){
            self.clear_search();
        };

        var search_timeout  = null;
        this.search_handler = function(event){
            if(event.type == "keypress" || event.keyCode === 46 || event.keyCode === 8){
                clearTimeout(search_timeout);

                var searchbox = this;

                search_timeout = setTimeout(function(){
                    self.perform_search(self.category, searchbox.value, event.which === 13);
                },70);
            }
        };
    },

    // changes the category. if undefined, sets to root category
    set_category : function(category){
        var db = this.pos.db;
        if(!category){
            this.category = db.get_category_by_id(db.root_category_id);
        }else{
            this.category = category;
        }
        this.breadcrumb = [];
        var ancestors_ids = db.get_category_ancestors_ids(this.category.id);
        for(var i = 1; i < ancestors_ids.length; i++){
            this.breadcrumb.push(db.get_category_by_id(ancestors_ids[i]));
        }
        if(this.category.id !== db.root_category_id){
            this.breadcrumb.push(this.category);
        }
        this.subcategories = db.get_category_by_id(db.get_category_childs_ids(this.category.id));
    },

    get_image_url: function(category){
        return window.location.origin + '/web/image?model=pos.category&field=image_medium&id='+category.id;
    },

    render_category: function( category, with_image ){
        var cached = this.category_cache.get_node(category.id);
        if(!cached){
            if(with_image){
                var image_url = this.get_image_url(category);
                var category_html = QWeb.render('CategoryButton',{ 
                        widget:  this, 
                        category: category, 
                        image_url: this.get_image_url(category),
                    });
                    category_html = _.str.trim(category_html);
                var category_node = document.createElement('div');
                    category_node.innerHTML = category_html;
                    category_node = category_node.childNodes[0];
            }else{
                var category_html = QWeb.render('CategorySimpleButton',{ 
                        widget:  this, 
                        category: category, 
                    });
                    category_html = _.str.trim(category_html);
                var category_node = document.createElement('div');
                    category_node.innerHTML = category_html;
                    category_node = category_node.childNodes[0];
            }
            this.category_cache.cache_node(category.id,category_node);
            return category_node;
        }
        return cached; 
    },

    replace: function($target){
        this.renderElement();
        var target = $target[0];
        target.parentNode.replaceChild(this.el,target);
    },

    renderElement: function(){

        var el_str  = QWeb.render(this.template, {widget: this});
        var el_node = document.createElement('div');

        el_node.innerHTML = el_str;
        el_node = el_node.childNodes[1];

        if(this.el && this.el.parentNode){
            this.el.parentNode.replaceChild(el_node,this.el);
        }

        this.el = el_node;

        var withpics = this.pos.config.iface_display_categ_images;

        var list_container = el_node.querySelector('.category-list');
        if (list_container) { 
            if (!withpics) {
                list_container.classList.add('simple');
            } else {
                list_container.classList.remove('simple');
            }
            for(var i = 0, len = this.subcategories.length; i < len; i++){
                list_container.appendChild(this.render_category(this.subcategories[i],withpics));
            }
        }

        var buttons = el_node.querySelectorAll('.js-category-switch');
        for(var i = 0; i < buttons.length; i++){
            buttons[i].addEventListener('click',this.switch_category_handler);
        }

        var products = this.pos.db.get_product_by_category(this.category.id); 
        this.product_list_widget.set_product_list(products); // FIXME: this should be moved elsewhere ... 

        this.el.querySelector('.searchbox input').addEventListener('keypress',this.search_handler);

        this.el.querySelector('.searchbox input').addEventListener('keydown',this.search_handler);

        this.el.querySelector('.search-clear').addEventListener('click',this.clear_search_handler);

        if(this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard){
            this.chrome.widget.keyboard.connect($(this.el.querySelector('.searchbox input')));
        }
    },
    
    // resets the current category to the root category
    reset_category: function(){
        this.set_category(this.pos.db.get_category_by_id(this.start_categ_id));
        this.renderElement();
    },

    // empties the content of the search box
    clear_search: function(){
        var products = this.pos.db.get_product_by_category(this.category.id);
        this.product_list_widget.set_product_list(products);
        var input = this.el.querySelector('.searchbox input');
            input.value = '';
            input.focus();
    },
    perform_search: function(category, query, buy_result){
        var products;
        if(query){
            products = this.pos.db.search_product_in_category(category.id,query);
            if(buy_result && products.length === 1){
                    this.pos.get_order().add_product(products[0]);
                    this.clear_search();
            }else{
                this.product_list_widget.set_product_list(products);
            }
        }else{
            products = this.pos.db.get_product_by_category(this.category.id);
            this.product_list_widget.set_product_list(products);
        }
    },

});

/* --------- The Product List --------- */

// Display the list of products. 
// - change the list with .set_product_list()
// - click_product_action(), passed as an option, tells
//   what to do when a product is clicked. 

var ProductListWidget = PosBaseWidget.extend({
    template:'ProductListWidget',
    init: function(parent, options) {
        var self = this;
        this._super(parent,options);
        this.model = options.model;
        this.productwidgets = [];
        this.weight = options.weight || 0;
        this.show_scale = options.show_scale || false;
        this.next_screen = options.next_screen || false;

        this.click_product_handler = function(){
            var product = self.pos.db.get_product_by_id(this.dataset.productId);
            options.click_product_action(product);
        };

        this.product_list = options.product_list || [];
        this.product_cache = new DomCache();

        this.pos.get('orders').bind('add remove change', function () {
            self.renderElement();
        }, this);

        this.pos.bind('change:selectedOrder', function () {
            this.renderElement();
        }, this);
    },
    set_product_list: function(product_list){
        this.product_list = product_list;
        this.renderElement();
    },
    get_product_image_url: function(product){
        return window.location.origin + '/web/image?model=product.product&field=image_medium&id='+product.id;
    },
    replace: function($target){
        this.renderElement();
        var target = $target[0];
        target.parentNode.replaceChild(this.el,target);
    },
    calculate_cache_key: function(product, pricelist){
        return product.id + ',' + pricelist.id;
    },
    _get_active_pricelist: function(){
        var current_order = this.pos.get_order();
        var current_pricelist = this.pos.default_pricelist;

        if (current_order) {
            current_pricelist = current_order.pricelist;
        }

        return current_pricelist;
    },
    render_product: function(product){
        var current_pricelist = this._get_active_pricelist();
        var cache_key = this.calculate_cache_key(product, current_pricelist);
        var cached = this.product_cache.get_node(cache_key);
        if(!cached){
            var image_url = this.get_product_image_url(product);
            var product_html = QWeb.render('Product',{ 
                    widget:  this, 
                    product: product,
                    pricelist: current_pricelist,
                    image_url: this.get_product_image_url(product),
                });
            var product_node = document.createElement('div');
            product_node.innerHTML = product_html;
            product_node = product_node.childNodes[1];
            this.product_cache.cache_node(cache_key,product_node);
            return product_node;
        }
        return cached;
    },

    renderElement: function() {
        var el_str  = QWeb.render(this.template, {widget: this});
        var el_node = document.createElement('div');
            el_node.innerHTML = el_str;
            el_node = el_node.childNodes[1];

        if(this.el && this.el.parentNode){
            this.el.parentNode.replaceChild(el_node,this.el);
        }
        this.el = el_node;

        var list_container = el_node.querySelector('.product-list');
        for(var i = 0, len = this.product_list.length; i < len; i++){
            var product_node = this.render_product(this.product_list[i]);
            product_node.addEventListener('click',this.click_product_handler);
            list_container.appendChild(product_node);
        }
    },
});

/* -------- The Action Buttons -------- */

// Above the numpad and the actionpad, buttons
// for extra actions and controls by point of
// sale extensions modules. 

var action_button_classes = [];
var define_action_button = function(classe, options){
    options = options || {};

    var classes = action_button_classes;
    var index   = classes.length;
    var i;

    if (options.after) {
        for (i = 0; i < classes.length; i++) {
            if (classes[i].name === options.after) {
                index = i + 1;
            }
        }
    } else if (options.before) {
        for (i = 0; i < classes.length; i++) {
            if (classes[i].name === options.after) {
                index = i;
                break;
            }
        }
    }
    classes.splice(i,0,classe);
};

var ActionButtonWidget = PosBaseWidget.extend({
    template: 'ActionButtonWidget',
    label: _t('Button'),
    renderElement: function(){
        var self = this;
        this._super();
        this.$el.click(function(){
            self.button_click();
        });
    },
    button_click: function(){},
    highlight: function(highlight){
        this.$el.toggleClass('highlight',!!highlight);
    },
    // alternative highlight color
    altlight: function(altlight){
        this.$el.toggleClass('altlight',!!altlight);
    },
});

/* -------- The Product Screen -------- */

var ProductScreenWidget = ScreenWidget.extend({
    template:'ProductScreenWidget',

    start: function(){ 

        var self = this;

        this.actionpad = new ActionpadWidget(this,{});
        this.actionpad.replace(this.$('.placeholder-ActionpadWidget'));

        this.numpad = new NumpadWidget(this,{});
        this.numpad.replace(this.$('.placeholder-NumpadWidget'));

        this.order_widget = new OrderWidget(this,{
            numpad_state: this.numpad.state,
        });
        this.order_widget.replace(this.$('.placeholder-OrderWidget'));

        this.product_list_widget = new ProductListWidget(this,{
            click_product_action: function(product){ self.click_product(product); },
            product_list: this.pos.db.get_product_by_category(0)
        });
        this.product_list_widget.replace(this.$('.placeholder-ProductListWidget'));

        this.product_categories_widget = new ProductCategoriesWidget(this,{
            product_list_widget: this.product_list_widget,
        });
        this.product_categories_widget.replace(this.$('.placeholder-ProductCategoriesWidget'));

        this.action_buttons = {};
        var classes = action_button_classes;
        for (var i = 0; i < classes.length; i++) {
            var classe = classes[i];
            if ( !classe.condition || classe.condition.call(this) ) {
                var widget = new classe.widget(this,{});
                widget.appendTo(this.$('.control-buttons'));
                this.action_buttons[classe.name] = widget;
            }
        }
        if (_.size(this.action_buttons)) {
            this.$('.control-buttons').removeClass('oe_hidden');
        }
    },

    click_product: function(product) {
       if(product.to_weight && this.pos.config.iface_electronic_scale){
           this.gui.show_screen('scale',{product: product});
       }else{
           this.pos.get_order().add_product(product);
       }
    },

    show: function(reset){
        this._super();
        if (reset) {
            this.product_categories_widget.reset_category();
            this.numpad.state.reset();
        }
        if (this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard) {
            this.chrome.widget.keyboard.connect($(this.el.querySelector('.searchbox input')));
        }
    },

    close: function(){
        this._super();
        if(this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard){
            this.chrome.widget.keyboard.hide();
        }
    },
});
gui.define_screen({name:'products', widget: ProductScreenWidget});

/*--------------------------------------*\
 |         THE CLIENT LIST              |
\*======================================*/

// The clientlist displays the list of customer,
// and allows the cashier to create, edit and assign
// customers.

var ClientListScreenWidget = ScreenWidget.extend({
    template: 'ClientListScreenWidget',

    init: function(parent, options){
        this._super(parent, options);
        this.partner_cache = new DomCache();
    },

    auto_back: true,

    show: function(){
        var self = this;
        this._super();

        this.renderElement();
        this.details_visible = false;
        this.old_client = this.pos.get_order().get_client();

        this.$('.back').click(function(){
            self.gui.back();
        });

        this.$('.next').click(function(){   
            self.save_changes();
            self.gui.back();    // FIXME HUH ?
        });

        this.$('.new-customer').click(function(){
            self.display_client_details('edit',{
                'country_id': self.pos.company.country_id,
                'provincia_id':false,
                'distrito_id':false,
            });
        });

        var partners = this.pos.db.get_partners_sorted(1000);
        this.render_list(partners);
        
        this.reload_partners();

        if( this.old_client ){
            this.display_client_details('show',this.old_client,0);
        }

        this.$('.client-list-contents').delegate('.client-line','click',function(event){
            self.line_select(event,$(this),parseInt($(this).data('id')));
        });

        var search_timeout = null;

        if(this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard){
            this.chrome.widget.keyboard.connect(this.$('.searchbox input'));
        }

        this.$('.searchbox input').on('keypress',function(event){
            clearTimeout(search_timeout);

            var searchbox = this;

            search_timeout = setTimeout(function(){
                self.perform_search(searchbox.value, event.which === 13);
            },70);
        });

        this.$('.searchbox .search-clear').click(function(){
            self.clear_search();
        });
    },

    hide: function () {
        this._super();
        this.new_client = null;
    },
    barcode_client_action: function(code){
        if (this.editing_client) {
            this.$('.detail.barcode').val(code.code);
        } else if (this.pos.db.get_partner_by_barcode(code.code)) {
            var partner = this.pos.db.get_partner_by_barcode(code.code);
            this.new_client = partner;
            this.display_client_details('show', partner);
        }
    },
    perform_search: function(query, associate_result){
        var customers;
        if(query){
            customers = this.pos.db.search_partner(query);
            this.display_client_details('hide');
            if ( associate_result && customers.length === 1){
                this.new_client = customers[0];
                this.save_changes();
                this.gui.back();
            }
            this.render_list(customers);
        }else{
            customers = this.pos.db.get_partners_sorted();
            this.render_list(customers);
        }
    },
    clear_search: function(){
        var customers = this.pos.db.get_partners_sorted(1000);
        this.render_list(customers);
        this.$('.searchbox input')[0].value = '';
        this.$('.searchbox input').focus();
    },
    render_list: function(partners){
        var contents = this.$el[0].querySelector('.client-list-contents');
        contents.innerHTML = "";
        for(var i = 0, len = Math.min(partners.length,1000); i < len; i++){
            var partner    = partners[i];
            var clientline = this.partner_cache.get_node(partner.id);
            if(!clientline){
                var clientline_html = QWeb.render('ClientLine',{widget: this, partner:partners[i]});
                var clientline = document.createElement('tbody');
                clientline.innerHTML = clientline_html;
                clientline = clientline.childNodes[1];
                this.partner_cache.cache_node(partner.id,clientline);
            }
            if( partner === this.old_client ){
                clientline.classList.add('highlight');
            }else{
                clientline.classList.remove('highlight');
            }
            contents.appendChild(clientline);
        }
    },
    save_changes: function(){
        var order = this.pos.get_order();
        if( this.has_client_changed() ){
            var default_fiscal_position_id = _.findWhere(this.pos.fiscal_positions, {'id': this.pos.config.default_fiscal_position_id[0]});
            if ( this.new_client ) {
                if (this.new_client.property_account_position_id ){
                  var client_fiscal_position_id = _.findWhere(this.pos.fiscal_positions, {'id': this.new_client.property_account_position_id[0]});
                  order.fiscal_position = client_fiscal_position_id || default_fiscal_position_id;
                }
                order.set_pricelist(_.findWhere(this.pos.pricelists, {'id': this.new_client.property_product_pricelist[0]}) || this.pos.default_pricelist);
            } else {
                order.fiscal_position = default_fiscal_position_id;
                order.set_pricelist(this.pos.default_pricelist);
            }

            order.set_client(this.new_client);
        }
    },
    has_client_changed: function(){
        if( this.old_client && this.new_client ){
            return this.old_client.id !== this.new_client.id;
        }else{
            return !!this.old_client !== !!this.new_client;
        }
    },
    toggle_save_button: function(){
        var $button = this.$('.button.next');
        if (this.editing_client) {
            $button.addClass('oe_hidden');
            return;
        } else if( this.new_client ){
            if( !this.old_client){
                $button.text(_t('Set Customer'));
            }else{
                $button.text(_t('Change Customer'));
            }
        }else{
            $button.text(_t('Deselect Customer'));
        }
        $button.toggleClass('oe_hidden',!this.has_client_changed());
    },
    line_select: function(event,$line,id){
        var partner = this.pos.db.get_partner_by_id(id);
        this.$('.client-list .lowlight').removeClass('lowlight');
        if ( $line.hasClass('highlight') ){
            $line.removeClass('highlight');
            $line.addClass('lowlight');
            this.display_client_details('hide',partner);
            this.new_client = null;
            this.toggle_save_button();
        }else{
            this.$('.client-list .highlight').removeClass('highlight');
            $line.addClass('highlight');
            var y = event.pageY - $line.parent().offset().top;
            this.display_client_details('show',partner,y);
            this.new_client = partner;
            this.toggle_save_button();
        }
    },
    partner_icon_url: function(id){
        return '/web/image?model=res.partner&id='+id+'&field=image_small';
    },

    // ui handle for the 'edit selected customer' action
    edit_client_details: function(partner) {
        this.display_client_details('edit',partner);
    },

    // ui handle for the 'cancel customer edit changes' action
    undo_client_details: function(partner) {
        if (!partner.id) {
            this.display_client_details('hide');
        } else {
            this.display_client_details('show',partner);
        }
    },

    // what happens when we save the changes on the client edit form -> we fetch the fields, sanitize them,
    // send them to the backend for update, and call saved_client_details() when the server tells us the
    // save was successfull.
    save_client_details: function(partner) {
        var self = this;
        
        var fields = {};
        this.$('.client-details-contents .detail').each(function(idx,el){
            fields[el.name] = el.value || false;
        });

        if (!fields.name) {
            this.gui.show_popup('error',_t('A Customer Name Is Required'));
            return;
        }
        
        if (this.uploaded_picture) {
            fields.image = this.uploaded_picture;
        }

        fields.id           = partner.id || false;
        fields.country_id   = fields.country_id || false;
        fields.state_id     = fields.state_id || false;
        fields.company_type = "company";
        fields.tipo_documento = "1";

        var tdoc = fields.vat;
        if (tdoc.length === 11){
            fields.tipo_documento = "6";
        }        
        fields.vat_mio = fields.vat;

        if (fields.property_product_pricelist) {
            fields.property_product_pricelist = parseInt(fields.property_product_pricelist, 10);
        } else {
            fields.property_product_pricelist = false;
        }

        rpc.query({
                model: 'res.partner',
                method: 'create_from_ui',
                args: [fields],
            })
            .then(function(partner_id){
                self.saved_client_details(partner_id);
            },function(type,err){
                var error_body = _t('Your Internet connection is probably down.');
                if (err.data) {
                    var except = err.data;
                    error_body = except.arguments && except.arguments[0] || except.message || error_body;
                }
                self.gui.show_popup('error',{
                    'title': _t('Error: Could not Save Changes'),
                    'body': error_body,
                });
            });
    },
    
    // what happens when we've just pushed modifications for a partner of id partner_id
    saved_client_details: function(partner_id){
        var self = this;
        this.reload_partners().then(function(){
            var partner = self.pos.db.get_partner_by_id(partner_id);
            if (partner) {
                self.new_client = partner;
                self.toggle_save_button();
                self.display_client_details('show',partner);
            } else {
                // should never happen, because create_from_ui must return the id of the partner it
                // has created, and reload_partner() must have loaded the newly created partner. 
                self.display_client_details('hide');
            }
        });
    },

    // resizes an image, keeping the aspect ratio intact,
    // the resize is useful to avoid sending 12Mpixels jpegs
    // over a wireless connection.
    resize_image_to_dataurl: function(img, maxwidth, maxheight, callback){
        img.onload = function(){
            var canvas = document.createElement('canvas');
            var ctx    = canvas.getContext('2d');
            var ratio  = 1;

            if (img.width > maxwidth) {
                ratio = maxwidth / img.width;
            }
            if (img.height * ratio > maxheight) {
                ratio = maxheight / img.height;
            }
            var width  = Math.floor(img.width * ratio);
            var height = Math.floor(img.height * ratio);

            canvas.width  = width;
            canvas.height = height;
            ctx.drawImage(img,0,0,width,height);

            var dataurl = canvas.toDataURL();
            callback(dataurl);
        };
    },

    // Loads and resizes a File that contains an image.
    // callback gets a dataurl in case of success.
    load_image_file: function(file, callback){
        var self = this;
        if (!file.type.match(/image.*/)) {
            this.gui.show_popup('error',{
                title: _t('Unsupported File Format'),
                body:  _t('Only web-compatible Image formats such as .png or .jpeg are supported'),
            });
            return;
        }
        
        var reader = new FileReader();
        reader.onload = function(event){
            var dataurl = event.target.result;
            var img     = new Image();
            img.src = dataurl;
            self.resize_image_to_dataurl(img,800,600,callback);
        };
        reader.onerror = function(){
            self.gui.show_popup('error',{
                title :_t('Could Not Read Image'),
                body  :_t('The provided file could not be read due to an unknown error'),
            });
        };
        reader.readAsDataURL(file);
    },

    // This fetches partner changes on the server, and in case of changes, 
    // rerenders the affected views
    reload_partners: function(){
        var self = this;
        return this.pos.load_new_partners().then(function(){
            self.render_list(self.pos.db.get_partners_sorted(1000));
            
            // update the currently assigned client if it has been changed in db.
            var curr_client = self.pos.get_order().get_client();
            if (curr_client) {
                self.pos.get_order().set_client(self.pos.db.get_partner_by_id(curr_client.id));
            }
        });
    },
    change_departamento: function(){
        var self = this;
        var prov_lst = self.pos.provincias;
        var IdDep = $("#departamento").val();
        
        var contenido = "<option value=''>Ninguno</option>";
        for (var i = 0; i < prov_lst.length; i++) {

            if (prov_lst[i].departamento_id[0] == IdDep){
                
                contenido = contenido + "<option value="+prov_lst[i].id+">"+prov_lst[i].name+"</option>"; // self.pos.provincias.push(prov_lst[i]);
            }
        }
        //alert(self.pos.partners[1].tipo_documento);
        $("#provincia").html(contenido);
        $("#distrito").html("<option value=''>Ninguno</option>");
    },
    change_provincia: function(){
        var self = this;
        var prov_lst = self.pos.distritos;
        var IdProv = $("#provincia").val();
        
        var contenido = "<option value=''>Ninguno</option>";
        for (var i = 0; i < prov_lst.length; i++) {

            if (prov_lst[i].provincia_id[0] == IdProv){
                
                contenido = contenido + "<option value="+prov_lst[i].id+">"+prov_lst[i].name+"</option>"; // self.pos.provincias.push(prov_lst[i]);
            }
        }

        $("#distrito").html(contenido);
    },
    change_rucdni: function(){
        var self = this;

        var vat = $('#ruc_dni').val();

        if (vat.length === 11 || vat.length === 8){
            var parametro = [];

            if (vat.length === 11){
                parametro.push('6');
            }else{
                parametro.push('1');
            }
            parametro.push(vat)
            
            rpc.query({model:'res.partner',
            method:'consultar_rucdni_bd',
            args:[parametro]
            }).then(function(result){
                //alert(result['name']);
                $('#raz_social').val(result['name']);
                $('#departamento').val(result['state_id']);
                self.change_departamento();
                $('#provincia').val(result['provincia_id']);
                self.change_provincia();
                $('#distrito').val(result['distrito_id']);
                $('#direccion').val(result['street']);
            });
        }
    },


    // Shows,hides or edit the customer details box :
    // visibility: 'show', 'hide' or 'edit'
    // partner:    the partner object to show or edit
    // clickpos:   the height of the click on the list (in pixel), used
    //             to maintain consistent scroll.
    display_client_details: function(visibility,partner,clickpos){
        var self = this;
        var searchbox = this.$('.searchbox input');
        var contents = this.$('.client-details-contents');
        var parent   = this.$('.client-list').parent();
        var scroll   = parent.scrollTop();
        var height   = contents.height();

        contents.off('click','.button.edit'); 
        contents.off('click','.button.save'); 
        contents.off('click','.button.undo'); 
        contents.on('click','.button.edit',function(){ self.edit_client_details(partner); });
        contents.on('click','.button.save',function(){ self.save_client_details(partner); });
        contents.on('click','.button.undo',function(){ self.undo_client_details(partner); });

        // DEPARTA
        contents.on('change','#ruc_dni',function(){ self.change_rucdni(); });
        contents.on('change','#departamento',function(){ self.change_departamento(); });
        contents.on('change','#provincia',function(){ self.change_provincia(); });

        this.editing_client = false;
        this.uploaded_picture = null;

        if(visibility === 'show'){
            contents.empty();
            contents.append($(QWeb.render('ClientDetails',{widget:this,partner:partner})));

            var new_height   = contents.height();

            if(!this.details_visible){
                // resize client list to take into account client details
                parent.height('-=' + new_height);

                if(clickpos < scroll + new_height + 20 ){
                    parent.scrollTop( clickpos - 20 );
                }else{
                    parent.scrollTop(parent.scrollTop() + new_height);
                }
            }else{
                parent.scrollTop(parent.scrollTop() - height + new_height);
            }

            this.details_visible = true;
            this.toggle_save_button();
        } else if (visibility === 'edit') {
            // Connect the keyboard to the edited field
            if (this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard) {
                contents.off('click', '.detail');
                searchbox.off('click');
                contents.on('click', '.detail', function(ev){
                    self.chrome.widget.keyboard.connect(ev.target);
                    self.chrome.widget.keyboard.show();
                });
                searchbox.on('click', function() {
                    self.chrome.widget.keyboard.connect($(this));
                });
            }

            this.editing_client = true;
            contents.empty();
            contents.append($(QWeb.render('ClientDetailsEdit',{widget:this,partner:partner})));
            this.toggle_save_button();

            // Browsers attempt to scroll invisible input elements
            // into view (eg. when hidden behind keyboard). They don't
            // seem to take into account that some elements are not
            // scrollable.
            contents.find('input').blur(function() {
                setTimeout(function() {
                    self.$('.window').scrollTop(0);
                }, 0);
            });

            contents.find('.image-uploader').on('change',function(event){
                self.load_image_file(event.target.files[0],function(res){
                    if (res) {
                        contents.find('.client-picture img, .client-picture .fa').remove();
                        contents.find('.client-picture').append("<img src='"+res+"'>");
                        contents.find('.detail.picture').remove();
                        self.uploaded_picture = res;
                    }
                });
            });
        } else if (visibility === 'hide') {
            contents.empty();
            parent.height('100%');
            if( height > scroll ){
                contents.css({height:height+'px'});
                contents.animate({height:0},400,function(){
                    contents.css({height:''});
                });
            }else{
                parent.scrollTop( parent.scrollTop() - height);
            }
            this.details_visible = false;
            this.toggle_save_button();
        }

        if (visibility === 'edit'){
            self.change_departamento();

            $('#provincia').val(partner.provincia_id[0]);
            self.change_provincia();
            $('#distrito').val(partner.distrito_id[0]);
        }
        //alert(partner.provincia_id);
    },
    close: function(){
        this._super();
        if (this.pos.config.iface_vkeyboard && this.chrome.widget.keyboard) {
            this.chrome.widget.keyboard.hide();
        }
    },
});
gui.define_screen({name:'clientlist', widget: ClientListScreenWidget});

/*--------------------------------------*\
 |         THE RECEIPT SCREEN           |
\*======================================*/

// The receipt screen displays the order's
// receipt and allows it to be printed in a web browser.
// The receipt screen is not shown if the point of sale
// is set up to print with the proxy. Altough it could
// be useful to do so...

var ReceiptScreenWidget = ScreenWidget.extend({
    template: 'ReceiptScreenWidget',
    show: function(){
        this._super();
        var self = this;        

        this.render_change();
        this.render_receipt();
        this.handle_auto_print();

        this.obtener_factura();
        
        //codigo prueba para agregar vendedor
        this.pos.captura_nombre_vendedor();
        //termina codigo prueba para agregar vendedor      
        
    },
    handle_auto_print: function() {
        if (this.should_auto_print()) {
            this.print();
            if (this.should_close_immediately()){
                this.click_next();
            }
        } else {
            this.lock_screen(false);
        }
    },
    should_auto_print: function() {
        return this.pos.config.iface_print_auto && !this.pos.get_order()._printed;
    },
    should_close_immediately: function() {
        return this.pos.config.iface_print_via_proxy && this.pos.config.iface_print_skip_screen;
    },
    lock_screen: function(locked) {
        this._locked = locked;
        if (locked) {
            this.$('.next').removeClass('highlight');
        } else {
            this.$('.next').addClass('highlight');
        }
    },
    get_receipt_render_env: function() {
        var order = this.pos.get_order();

        
        return {
            widget: this,
            pos: this.pos,
            order: order,
            receipt: order.export_for_printing(),
            orderlines: order.get_orderlines(),
            paymentlines: order.get_paymentlines(),
            
        };
    },

    

    obtener_factura: function() {
        var dato = this.pos.db.get_order_server_id();
        var self = this; 

        
        rpc.query({ model: 'pos.order',
        method: 'buscar_factura',
        args: [dato],
        })
        .then(function(result){       
            $('.comprobante_nombre').html(result['txt_factura']);
            $('#factura_num_serie').html(result['numeracion_factura']);
            var baseStr64 = result['qrcode'];
            var logo_b64 = result['logo_emp'];

            miqr.setAttribute('src', "data:image/jpg;base64," + baseStr64);
            
            self.pos.get_order().set_pdf_b64(result['pdf_reporte'])

            try {
                logo_emp.setAttribute('src', "data:image/jpg;base64," + logo_b64);
            } catch (error){

            }

            //para mostrar el cliente en el ticket
            $('#cliente_default').html(result['cliente']);
            $('#pagina_custodia').html(result['pag_custodia']);           
        });

    },
      
    print_web: function() {
        window.print();
        this.pos.get_order()._printed = true;
    },
    print_xml: function() {
        var receipt = QWeb.render('XmlReceipt', this.get_receipt_render_env());

        this.pos.proxy.print_receipt(receipt);
        this.pos.get_order()._printed = true;
    },
    print: function() {
        var self = this;

        if (this.pos.company.imprimir_comprobante){
            self.print_pdf();

        }else {

            if (!this.pos.config.iface_print_via_proxy) { // browser (html) printing

                // The problem is that in chrome the print() is asynchronous and doesn't
                // execute until all rpc are finished. So it conflicts with the rpc used
                // to send the orders to the backend, and the user is able to go to the next 
                // screen before the printing dialog is opened. The problem is that what's 
                // printed is whatever is in the page when the dialog is opened and not when it's called,
                // and so you end up printing the product list instead of the receipt... 
                //
                // Fixing this would need a re-architecturing
                // of the code to postpone sending of orders after printing.
                //
                // But since the print dialog also blocks the other asynchronous calls, the
                // button enabling in the setTimeout() is blocked until the printing dialog is 
                // closed. But the timeout has to be big enough or else it doesn't work
                // 1 seconds is the same as the default timeout for sending orders and so the dialog
                // should have appeared before the timeout... so yeah that's not ultra reliable. 

                this.lock_screen(true);

                setTimeout(function(){
                    self.lock_screen(false);
                }, 1000);

                this.print_web();
            } else {    // proxy (xml) printing
                this.print_xml();
                this.lock_screen(false);
            }


        }
    },
    click_next: function() {
        this.pos.get_order().finalize();
    },
    click_back: function() {
        // Placeholder method for ReceiptScreen extensions that
        // can go back ...
    },
    print_pdf: function() {
        //var self = this;
        
        var self = this;
        var pdfText = self.pos.get_order().get_pdf_b64();        

        //alert(pdfText);

        pdfText = atob(pdfText);
        //pdfText = $.base64.decode($.trim(pdfText));

        // Now pdfText contains %PDF-1.4 ...... data...... %%EOF

        var winlogicalname = "detailPDF";
        var winparams = 'dependent=yes,locationbar=no,scrollbars=yes,menubar=yes,'+
                    'resizable,screenX=50,screenY=50,width=850,height=1050';

        var htmlText = '<embed width=100% height=100%'
                             + ' type="application/pdf"'
                             + ' src="data:application/pdf,'
                             + escape(pdfText)
                             + '"></embed>'; 

                // Open PDF in new browser window
        var detailWindow = window.open ("", winlogicalname, winparams);
        detailWindow.document.write(htmlText);
        detailWindow.document.close();
        
    },
    renderElement: function() {
        var self = this;
        this._super();
        this.$('.next').click(function(){
            if (!self._locked) {
                self.click_next();
            }
        });
        this.$('.back').click(function(){
            if (!self._locked) {
                self.click_back();
            }
        });
        this.$('.button.print').click(function(){
            if (!self._locked) {
                self.print();
            }
        });
        
    },
    render_change: function() {
        this.$('.change-value').html(this.format_currency(this.pos.get_order().get_change()));
    },
    render_receipt: function() {
        this.$('.pos-receipt-container').html(QWeb.render('PosTicket', this.get_receipt_render_env()));
    },
});
gui.define_screen({name:'receipt', widget: ReceiptScreenWidget});

/*--------------------------------------*\
 |         THE PAYMENT SCREEN           |
\*======================================*/

// The Payment Screen handles the payments, and
// it is unfortunately quite complicated.

var PaymentScreenWidget = ScreenWidget.extend({
    template:      'PaymentScreenWidget',
    back_screen:   'product',
    init: function(parent, options) {
        var self = this;
        this._super(parent, options);

        this.pos.bind('change:selectedOrder',function(){
                this.renderElement();
                this.watch_order_changes();
            },this);
        this.watch_order_changes();

        this.inputbuffer = "";
        this.firstinput  = true;
        this.decimal_point = _t.database.parameters.decimal_point;
        
        
        // This is a keydown handler that prevents backspace from
        // doing a back navigation. It also makes sure that keys that
        // do not generate a keypress in Chrom{e,ium} (eg. delete,
        // backspace, ...) get passed to the keypress handler.
        this.keyboard_keydown_handler = function(event){
            //var key = ""
            var target_element = event['target']['id'];
            if (target_element == 'observacion' || target_element == 'nro_guia' || target_element == 'nro_placa'){

                $('#observacion').on('input', function () { 
                    //this.value = this.value.replace(/[^0-9]/g,'');
                    
                });                               
                
                
            }

            else {
                console.log("Escribiendo sobre el Pago");
                if (event.keyCode === 8 || event.keyCode === 46) { // Backspace and Delete
                    event.preventDefault();
                    self.keyboard_handler(event);
                }
            }
        };

        

        
        // This keyboard handler listens for keypress events. It is
        // also called explicitly to handle some keydown events that
        // do not generate keypress events.
        this.keyboard_handler = function(event){
            var key = '';
            var target_element = event['target']['id'];
            if (target_element != 'observacion' && target_element != 'nro_guia' && target_element != 'nro_placa'){

                if (event.type === "keypress") {
                    if (event.keyCode === 13) { // Enter
                        self.validate_order();
                    } else if ( event.keyCode === 190 || // Dot
                                event.keyCode === 110 ||  // Decimal point (numpad)
                                event.keyCode === 188 ||  // Comma
                                event.keyCode === 46 ) {  // Numpad dot
                        key = self.decimal_point;
                    } else if (event.keyCode >= 48 && event.keyCode <= 57) { // Numbers
                        key = '' + (event.keyCode - 48);
                    } else if (event.keyCode === 45) { // Minus
                        key = '-';
                    } else if (event.keyCode === 43) { // Plus
                        key = '+';
                    }
                } else { // keyup/keydown
                    if (event.keyCode === 46) { // Delete
                        key = 'CLEAR';
                    } else if (event.keyCode === 8) { // Backspace
                        key = 'BACKSPACE';
                    }
                }

                self.payment_input(key);
                event.preventDefault();
            }
        };

        this.pos.bind('change:selectedClient', function() {
            self.customer_changed();
        }, this);
    },   

    
    // resets the current input buffer
    reset_input: function(){
        var line = this.pos.get_order().selected_paymentline;
        this.firstinput  = true;
        if (line) {
            this.inputbuffer = this.format_currency_no_symbol(line.get_amount());
        } else {
            this.inputbuffer = "";
        }
    },
    // handle both keyboard and numpad input. Accepts
    // a string that represents the key pressed.
    payment_input: function(input) {
        var newbuf = this.gui.numpad_input(this.inputbuffer, input, {'firstinput': this.firstinput});

        this.firstinput = (newbuf.length === 0);

        // popup block inputs to prevent sneak editing. 
        if (this.gui.has_popup()) {
            return;
        }
        
        if (newbuf !== this.inputbuffer) {
            this.inputbuffer = newbuf;
            var order = this.pos.get_order();
            if (order.selected_paymentline) {
                var amount = this.inputbuffer;

                if (this.inputbuffer !== "-") {
                    amount = field_utils.parse.float(this.inputbuffer);
                }

                order.selected_paymentline.set_amount(amount);               

                this.order_changes();
                this.render_paymentlines();
                this.$('.paymentline.selected .edit').text(this.format_currency_no_symbol(amount));
            }
        }
    },

    change_observacion: function(){
        this.pos.get_order().selected_paymentline.set_observacion(this.$('#observacion').val())
    },
    input_observacion: function(){
        if (this.pos.get_order().selected_paymentline){
            this.$('#observacion').val(this.pos.get_order().selected_paymentline.get_observacion());
        }
    },

    // Nro de guía.
    change_guia_nro: function(){
        this.pos.get_order().set_guia_nro(this.$('#nro_guia'.val()))
    },
    input_guia_nro: function(){
        if (this.pos.get_order()){
            this.$('#nro_guia').val(this.pos.get_order().get_guia_nro());
        }
    },

    // Nro de placa.
    change_placa_nro: function(){
        this.pos.get_order().set_placa_nro(this.$('#nro_placa'.val()))
    },
    input_placa_nro: function(){
        if (this.pos.get_order()){
            this.$('#nro_placa').val(this.pos.get_order().get_placa_nro());
        }
    },

    click_numpad: function(button) {
    	var paymentlines = this.pos.get_order().get_paymentlines();
    	var open_paymentline = false;

    	for (var i = 0; i < paymentlines.length; i++) {
    	    if (! paymentlines[i].paid) {
    		open_paymentline = true;
    	    }
    	}

    	if (! open_paymentline) {
            this.pos.get_order().add_paymentline( this.pos.cashregisters[0]);
            this.render_paymentlines();
        }

        this.payment_input(button.data('action'));

        this.input_observacion();


        
    },
    render_numpad: function() {
        var self = this;
        var numpad = $(QWeb.render('PaymentScreen-Numpad', { widget:this }));
        numpad.on('click','button',function(){
            self.click_numpad($(this));
        });
        return numpad;
    },
    click_delete_paymentline: function(cid){
        var lines = this.pos.get_order().get_paymentlines();
        for ( var i = 0; i < lines.length; i++ ) {
            if (lines[i].cid === cid) {
                this.pos.get_order().remove_paymentline(lines[i]);
                this.reset_input();
                this.render_paymentlines();

                this.input_observacion();

                return;
            }
        }
    },
    click_paymentline: function(cid){
        var lines = this.pos.get_order().get_paymentlines();
        for ( var i = 0; i < lines.length; i++ ) {
            if (lines[i].cid === cid) {
                this.pos.get_order().select_paymentline(lines[i]);
                this.reset_input();
                this.render_paymentlines();

                this.input_observacion();

                return;
            }
        }
    },
    render_paymentlines: function() {
        var self  = this;
        var order = this.pos.get_order();
        if (!order) {
            return;
        }

        var lines = order.get_paymentlines();
        var due   = order.get_due();
        var extradue = 0;
        if (due && lines.length  && due !== order.get_due(lines[lines.length-1])) {
            extradue = due;
        }


        this.$('.paymentlines-container').empty();
        var lines = $(QWeb.render('PaymentScreen-Paymentlines', { 
            widget: this, 
            order: order,
            paymentlines: lines,
            extradue: extradue,
        }));

        lines.on('click','.delete-button',function(){
            self.click_delete_paymentline($(this).data('cid'));
        });

        lines.on('click','.paymentline',function(){
            self.click_paymentline($(this).data('cid'));
        });

        lines.on('change','#observacion',function(){
            self.change_observacion();
        });

        lines.appendTo(this.$('.paymentlines-container'));
    },
    click_paymentmethods: function(id) {
        var cashregister = null;
        for ( var i = 0; i < this.pos.cashregisters.length; i++ ) {
            if ( this.pos.cashregisters[i].journal_id[0] === id ){
                cashregister = this.pos.cashregisters[i];
                break;
            }
        }
        this.pos.get_order().add_paymentline( cashregister );
        this.reset_input();
        this.render_paymentlines();

        this.input_observacion();
    },
    render_paymentmethods: function() {
        var self = this;
        var methods = $(QWeb.render('PaymentScreen-Paymentmethods', { widget:this }));
            methods.on('click','.paymentmethod',function(){
                self.click_paymentmethods($(this).data('id'));
            });
        return methods;
    },

    click_invoice: function(){
        var order = this.pos.get_order();

        if (!order.is_to_invoice()){
             order.set_to_invoice(!order.is_to_invoice());
            if (order.is_to_invoice()) {
                this.$('.js_invoice').addClass('highlight');
            
            } else {
                this.$('.js_invoice').removeClass('highlight');
            
            }    

            if (order.is_to_invoice2()) {
                order.set_to_invoice2(!order.is_to_invoice2());
                this.$('.js_invoice2').removeClass('highlight');

            }
        }
    },
    click_invoice2: function(){
        var order = this.pos.get_order();

        if (!order.is_to_invoice2()){
            order.set_to_invoice2(!order.is_to_invoice2());


            if (order.is_to_invoice2()) {           
               this.$('.js_invoice2').addClass('highlight');
            } else {     
                this.$('.js_invoice2').removeClass('highlight');
            }

            if (order.is_to_invoice()) {
                order.set_to_invoice(!order.is_to_invoice());
                this.$('.js_invoice').removeClass('highlight');
            }
        }
    },

    click_descarga: function(dato){
        //alert("hola" )
        //return
        // responseText encoding 
        var pdfText ='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IAo0NzMgCjQ5NSAKNjUzIAo1OTEgCjAgCjAgCjUyMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMjY3IAowIAowIAowIAowIAowIAo2NzYgCl0gCmVuZG9iaiAKMTkgMCBvYmogCjw8IAovVHlwZSAvRm9udERlc2NyaXB0b3IgCi9Bc2NlbnQgOTUyIAovQ2FwSGVpZ2h0IDUwMCAKL0Rlc2NlbnQgLTI2OSAKL0ZsYWdzIDQgCi9Gb250QkJveCAyMCAwIFIgCi9Gb250TmFtZSAvQUFBQUFBK0NhbGlicmksQm9sZCAKL0l0YWxpY0FuZ2xlIDAKL1N0ZW1WIDAgCi9TdGVtSCAwIAovQXZnV2lkdGggNTM2IAovRm9udEZpbGUyIDIxIDAgUiAKL0xlYWRpbmcgMCAKL01heFdpZHRoIDE3ODEgCi9NaXNzaW5nV2lkdGggNTM2IAovWEhlaWdodCAwIAo+PiAKZW5kb2JqIAoyMCAwIG9iaiAKWyAtNTE5IC0zNDkgMTI2MyAxMDM5IF0gCmVuZG9iaiAKMjIgMCBvYmogClsgCjIyNiAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMzAzIAozMDMgCjAgCjAgCjI1MCAKMzA2IAoyNTIgCjM4NiAKNTA3IAo1MDcgCjUwNyAKNTA3IAo1MDcgCjUwNyAKNTA3IAo1MDcgCjUwNyAKMCAKMjY4IAowIAowIAowIAowIAowIAo4OTQgCjU3OSAKNTQ0IAo1MzMgCjYxNSAKNDg4IAo0NTkgCjAgCjYyMyAKMjUyIAowIAo1MjAgCjQyMCAKODU1IAo2NDYgCjY2MiAKNTE3IAowIAo1NDMgCjQ1OSAKNDg3IAo2NDIgCjU2NyAKMCAKNTE5IAowIAo0NjggCjAgCjAgCjAgCjAgCjAgCjAgCjQ3OSAKNTI1IAo0MjMgCjUyNSAKNDk4IAozMDUgCjAgCjAgCjIzMCAKMCAKMCAKMjMwIAo3OTkgCjUyNSAKNTI3IAo1MjUgCjAgCjM0OSAKMzkxIAozMzUgCjUyNSAKNDUyIAo3MTUgCjAgCjQ1MyAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKMCAKNjQ2IApdIAplbmRvYmogCjI0IDAgb2JqIAo8PCAKL1R5cGUgL0ZvbnREZXNjcmlwdG9yIAovQXNjZW50IDk1MiAKL0NhcEhlaWdodCA1MDAgCi9EZXNjZW50IC0yNjkgCi9GbGFncyA0IAovRm9udEJCb3ggMjUgMCBSIAovRm9udE5hbWUgL0FBQUFBQitDYWxpYnJpIAovSXRhbGljQW5nbGUgMAovU3RlbVYgMCAKL1N0ZW1IIDAgCi9BdmdXaWR0aCA1MjEgCi9Gb250RmlsZTIgMjYgMCBSIAovTGVhZGluZyAwIAovTWF4V2lkdGggMTc0MyAKL01pc3NpbmdXaWR0aCA1MjEgCi9YSGVpZ2h0IDAgCj4+IAplbmRvYmogCjI1IDAgb2JqIApbIC01MDMgLTMxMyAxMjQwIDEwMjYgXSAKZW5kb2JqIAoyNyAwIG9iaiAKKFBvd2VyZWQgQnkgQ3J5c3RhbCkgCmVuZG9iaiAKMjggMCBvYmogCihDcnlzdGFsIFJlcG9ydHMpIAplbmRvYmogCjI5IDAgb2JqIAo8PCAKL1Byb2R1Y2VyIChQb3dlcmVkIEJ5IENyeXN0YWwpICAKL0NyZWF0b3IgKENyeXN0YWwgUmVwb3J0cykgIAo+PiAKZW5kb2JqIAp4cmVmIAowIDMwIAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTcgMDAwMDAgbiAKMDAwMDAzMzE4NiAwMDAwMCBuIAowMDAwMDMzMjg1IDAwMDAwIG4gCjAwMDAwMzMzMTkgMDAwMDAgbiAKMDAwMDAwMDE5NCAwMDAwMCBuIAowMDAwMDMzMzUzIDAwMDAwIG4gCjAwMDAwMzM0NzggMDAwMDAgbiAKMDAwMDAzMzUzNiAwMDAwMCBuIAowMDAwMDMzNjI4IDAwMDAwIG4gCjAwMDAwMzM4MDcgMDAwMDAgbiAKMDAwMDAzNjUzNiAwMDAwMCBuIAowMDAwMDM2NTkwIDAwMDAwIG4gCjAwMDAwMzY4MDggMDAwMDAgbiAKMDAwMDAzNjk4MyAwMDAwMCBuIAowMDAwMDQxMDI0IDAwMDAwIG4gCjAwMDAwNDEwNzggMDAwMDAgbiAKMDAwMDA0MTE4NCAwMDAwMCBuIAowMDAwMDAxNTA0IDAwMDAwIG4gCjAwMDAwNDE4MTQgMDAwMDAgbiAKMDAwMDA0MjA5NSAwMDAwMCBuIAowMDAwMDAyMDMwIDAwMDAwIG4gCjAwMDAwNDIxMzggMDAwMDAgbiAKMDAwMDAxMzEzOCAwMDAwMCBuIAowMDAwMDQyODE0IDAwMDAwIG4gCjAwMDAwNDMwOTAgMDAwMDAgbiAKMDAwMDAxMzg0MSAwMDAwMCBuIAowMDAwMDQzMTMzIDAwMDAwIG4gCjAwMDAwNDMxNzMgMDAwMDAgbiAKMDAwMDA0MzIxMCAwMDAwMCBuIAp0cmFpbGVyIAo8PCAKL1NpemUgMzAgCi9Sb290IDEgMCBSIAovSW5mbyAyOSAwIFIgCj4+IApzdGFydHhyZWYgCjQzMjk4IAolJUVPRg0K';


        pdfText = atob(pdfText);
        //pdfText = $.base64.decode($.trim(pdfText));

        // Now pdfText contains %PDF-1.4 ...... data...... %%EOF

        var winlogicalname = "detailPDF";
        var winparams = 'dependent=yes,locationbar=no,scrollbars=yes,menubar=yes,'+
                    'resizable,screenX=50,screenY=50,width=850,height=1050';

        var htmlText = '<embed width=100% height=100%'
                             + ' type="application/pdf"'
                             + ' src="data:application/pdf,'
                             + escape(pdfText)
                             + '"></embed>'; 

                // Open PDF in new browser window
        var detailWindow = window.open ("", winlogicalname, winparams);
        detailWindow.document.write(htmlText);
        detailWindow.document.close();

    },

    click_tip: function(){
        var self   = this;
        var order  = this.pos.get_order();
        var tip    = order.get_tip();
        var change = order.get_change();
        var value  = tip;

        if (tip === 0 && change > 0  ) {
            value = change;
        }

        this.gui.show_popup('number',{
            'title': tip ? _t('Change Tip') : _t('Add Tip'),
            'value': self.format_currency_no_symbol(value),
            'confirm': function(value) {
                order.set_tip(field_utils.parse.float(value));
                self.order_changes();
                self.render_paymentlines();
            }
        });
    },

    customer_changed: function() {
        var client = this.pos.get_client();
        this.$('.js_customer_name').text( client ? client.name : _t('Customer') ); 
    },
    click_set_customer: function(){
        this.gui.show_screen('clientlist');
    },
    click_back: function(){
        this.gui.show_screen('products');
    },
    renderElement: function() {
        var self = this;
        this._super();

        //var depa = this.render_departamento();
        //depa.appendTo(this.$('.ruc_dni'));

        var numpad = this.render_numpad();
        numpad.appendTo(this.$('.payment-numpad'));

        var methods = this.render_paymentmethods();
        methods.appendTo(this.$('.paymentmethods-container'));

        this.render_paymentlines();

        this.$('.back').click(function(){
            self.click_back();
        });

        this.$('.next').click(function(){
            self.validate_order();
            //self.click_descarga();
        
        });

        this.$('.js_set_customer').click(function(){
            self.click_set_customer();
        });

        this.$('.js_tip').click(function(){
            self.click_tip();
        });
        this.$('.js_invoice').click(function(){
            self.click_invoice();
        });
        this.$('.js_invoice2').click(function(){
            self.click_invoice2();
        });
        this.$('.mi_descarga').click(function(){
            self.click_descarga();
        });

        this.$('.js_cashdrawer').click(function(){
            self.pos.proxy.open_cashbox();
        });

    },
    show: function(){
        this.pos.get_order().clean_empty_paymentlines();
        this.reset_input();
        this.render_paymentlines();
        this.order_changes();
        // that one comes from BarcodeEvents
        $('body').keypress(this.keyboard_handler);
        // that one comes from the pos, but we prefer to cover all the basis
        $('body').keydown(this.keyboard_keydown_handler);
        // legacy vanilla JS listeners
        window.document.body.addEventListener('keypress',this.keyboard_handler);
        window.document.body.addEventListener('keydown',this.keyboard_keydown_handler);
        this._super();
    },
    hide: function(){
        $('body').off('keypress', this.keyboard_handler);
        $('body').off('keydown', this.keyboard_keydown_handler);
        window.document.body.removeEventListener('keypress',this.keyboard_handler);
        window.document.body.removeEventListener('keydown',this.keyboard_keydown_handler);
        this._super();
    },
    // sets up listeners to watch for order changes
    watch_order_changes: function() {
        var self = this;
        var order = this.pos.get_order();
        if (!order) {
            return;
        }
        if(this.old_order){
            this.old_order.unbind(null,null,this);
        }
        order.bind('all',function(){
            self.order_changes();
        });
        this.old_order = order;
    },
    // called when the order is changed, used to show if
    // the order is paid or not
    order_changes: function(){
        var self = this;
        var order = this.pos.get_order();
        if (!order) {
            return;
        } else if (order.is_paid()) {
            self.$('.next').addClass('highlight');
        }else{
            self.$('.next').removeClass('highlight');
        }
    },

    order_is_valid: function(force_validation) {
        var self = this;
        var order = this.pos.get_order();

        // FIXME: this check is there because the backend is unable to
        // process empty orders. This is not the right place to fix it.
        if (order.get_orderlines().length === 0) {
            this.gui.show_popup('error',{
                'title': _t('Empty Order'),
                'body':  _t('There must be at least one product in your order before it can be validated'),
            });
            return false;
        }

        if (!order.is_paid() || this.invoicing) {
            return false;
        }

        // The exact amount must be paid if there is no cash payment method defined.
        if (Math.abs(order.get_total_with_tax() - order.get_total_paid()) > 0.00001) {
            var cash = false;
            for (var i = 0; i < this.pos.cashregisters.length; i++) {
                cash = cash || (this.pos.cashregisters[i].journal.type === 'cash');
            }
            if (!cash) {
                this.gui.show_popup('error',{
                    title: _t('Cannot return change without a cash payment method'),
                    body:  _t('There is no cash payment method available in this point of sale to handle the change.\n\n Please pay the exact amount or add a cash payment method in the point of sale configuration'),
                });
                return false;
            }
        }

        // if the change is too large, it's probably an input error, make the user confirm.
        if (!force_validation && order.get_total_with_tax() > 0 && (order.get_total_with_tax() * 1000 < order.get_total_paid())) {
            this.gui.show_popup('confirm',{
                title: _t('Please Confirm Large Amount'),
                body:  _t('Are you sure that the customer wants to  pay') + 
                       ' ' + 
                       this.format_currency(order.get_total_paid()) +
                       ' ' +
                       _t('for an order of') +
                       ' ' +
                       this.format_currency(order.get_total_with_tax()) +
                       ' ' +
                       _t('? Clicking "Confirm" will validate the payment.'),
                confirm: function() {
                    self.validate_order('confirm');
                },
            });
            return false;
        }

        return true;
    },

    finalize_validation: function() {
        var self = this;
        var order = this.pos.get_order();

        //actualizar el vendedor
        order.set_vendedor_id();
        order.set_guia_nro();
        order.set_placa_nro();
        //

        if (order.is_paid_with_cash() && this.pos.config.iface_cashdrawer) { 

            this.pos.proxy.open_cashbox();
        }

        order.initialize_validation_date();
        order.finalized = true;

        if (order.is_to_invoice() || order.is_to_invoice2()) {
            var invoiced = this.pos.push_and_invoice_order(order);
            this.invoicing = true;
            invoice_id = this.pos.invoice_id

            invoiced.fail(function(error){
                self.invoicing = false;
                order.finalized = false;
                if (error.message === 'Missing Customer') {
                    self.gui.show_popup('confirm',{
                        'title': _t('Please select the Customer'),
                        'body': _t('You need to select the customer before you can invoice an order.'),
                        confirm: function(){
                            self.gui.show_screen('clientlist');
                        },
                    });
                } else if (error.code < 0) {        // XmlHttpRequest Errors
                    self.gui.show_popup('error',{
                        'title': _t('The order could not be sent'),
                        'body': _t('Check your internet connection and try again.'),
                    });
                } else if (error.code === 200) {    // OpenERP Server Errors
                    self.gui.show_popup('error-traceback',{
                        'title': error.data.message || _t("Server Error"),
                        'body': error.data.debug || _t('The server encountered an error while receiving your order.'),
                    });
                } else {                            // ???
                    self.gui.show_popup('error',{
                        'title': _t("Unknown Error"),
                        'body':  _t("The order could not be sent to the server due to an unknown error"),
                    });
                }
            });

            invoiced.done(function(){                
                self.invoicing = false;
                self.gui.show_screen('receipt');
            });
        } else {
            this.pos.push_order(order);
            this.gui.show_screen('receipt');
        }

    },

    // Check if the order is paid, then sends it to the backend,
    // and complete the sale process
    validate_order: function(force_validation) {
        if (this.order_is_valid(force_validation)) {
            this.finalize_validation();
            //this.ejecutar()
        }
    },
    
});

gui.define_screen({name:'payment', widget: PaymentScreenWidget});

var set_fiscal_position_button = ActionButtonWidget.extend({
    template: 'SetFiscalPositionButton',
    init: function (parent, options) {
        this._super(parent, options);

        this.pos.get('orders').bind('add remove change', function () {
            this.renderElement();
        }, this);

        this.pos.bind('change:selectedOrder', function () {
            this.renderElement();
        }, this);
    },
    button_click: function () {
        var self = this;

        var no_fiscal_position = [{
            label: _t("None"),
        }];
        var fiscal_positions = _.map(self.pos.fiscal_positions, function (fiscal_position) {
            return {
                label: fiscal_position.name,
                item: fiscal_position
            };
        });

        var selection_list = no_fiscal_position.concat(fiscal_positions);
        self.gui.show_popup('selection',{
            title: _t('Select tax'),
            list: selection_list,
            confirm: function (fiscal_position) {
                var order = self.pos.get_order();
                order.fiscal_position = fiscal_position;
                // This will trigger the recomputation of taxes on order lines.
                // It is necessary to manually do it for the sake of consistency
                // with what happens when changing a customer. 
                _.each(order.orderlines.models, function (line) {
                    line.set_quantity(line.quantity);
                });
                order.trigger('change');
            },
            is_selected: function (fiscal_position) {
                return fiscal_position === self.pos.get_order().fiscal_position;
            }
        });
    },
    get_current_fiscal_position_name: function () {
        var name = _t('Tax');
        var order = this.pos.get_order();

        if (order) {
            var fiscal_position = order.fiscal_position;

            if (fiscal_position) {
                name = fiscal_position.display_name;
            }
        }
         return name;
    },
});

define_action_button({
    'name': 'set_fiscal_position',
    'widget': set_fiscal_position_button,
    'condition': function(){
        return this.pos.fiscal_positions.length > 0;
    },
});

var set_pricelist_button = ActionButtonWidget.extend({
    template: 'SetPricelistButton',
    init: function (parent, options) {
        this._super(parent, options);

        this.pos.get('orders').bind('add remove change', function () {
            this.renderElement();
        }, this);

        this.pos.bind('change:selectedOrder', function () {
            this.renderElement();
        }, this);
    },
    button_click: function () {
        var self = this;

        var pricelists = _.map(self.pos.pricelists, function (pricelist) {
            return {
                label: pricelist.name,
                item: pricelist
            };
        });

        self.gui.show_popup('selection',{
            title: _t('Select pricelist'),
            list: pricelists,
            confirm: function (pricelist) {
                var order = self.pos.get_order();
                order.set_pricelist(pricelist);
            },
            is_selected: function (pricelist) {
                return pricelist.id === self.pos.get_order().pricelist.id;
            }
        });
    },
    get_current_pricelist_name: function () {
        var name = _t('Pricelist');
        var order = this.pos.get_order();

        if (order) {
            var pricelist = order.pricelist;

            if (pricelist) {
                name = pricelist.display_name;
            }
        }
         return name;
    },
});

define_action_button({
    'name': 'set_pricelist',
    'widget': set_pricelist_button,
    'condition': function(){
        return this.pos.pricelists.length > 1;
    },
});

return {
    ReceiptScreenWidget: ReceiptScreenWidget,
    ActionButtonWidget: ActionButtonWidget,
    define_action_button: define_action_button,
    ScreenWidget: ScreenWidget,
    PaymentScreenWidget: PaymentScreenWidget,
    OrderWidget: OrderWidget,
    NumpadWidget: NumpadWidget,
    ProductScreenWidget: ProductScreenWidget,
    ProductListWidget: ProductListWidget,
    ClientListScreenWidget: ClientListScreenWidget,
    ActionpadWidget: ActionpadWidget,
    DomCache: DomCache,
    ProductCategoriesWidget: ProductCategoriesWidget,
    ScaleScreenWidget: ScaleScreenWidget,
    set_fiscal_position_button: set_fiscal_position_button,
    set_pricelist_button: set_pricelist_button,
};

});
