# -*- encoding: utf-8 -*-
##############################################################################
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see http://www.gnu.org/licenses/.
#
##############################################################################

from openerp import models, fields, api, exceptions, _
from openerp.addons import decimal_precision as dp


class ProductAttributeValueSaleLine(models.Model):
    _name = 'sale.order.line.attribute'

           
    # ANADIDO PARA QUE MUESTRE LA CANTIDAD DE LA MATERIA PRIMA, RELACIONADO CON MRP_BOM_ATTRIBUTES
    @api.one 
    @api.depends('value', 'sale_line.product_template', 'size_x','size_y','size_z') 
    def _get_qty(self): 
        mp_qty = 1
        for mpqty in self.value.price_ids:
            if mpqty.product_tmpl_id.id == self.sale_line.product_template.id:
                mp_qty = mpqty.raw_qty
        self.mp_qty = 1 * self.size_x * self.size_y * self.size_z

    @api.one
    @api.depends('value', 'sale_line.product_template', 'mp_qty')
    def _get_price_extra(self):
        price_extra = 0.0
        for price in self.value.price_ids:
            if price.product_tmpl_id.id == self.sale_line.product_template.id:
                price_extra = price.price_extra
        self.price_extra = price_extra * self.mp_qty

    #@depends('value', 'discount')
    #def _apply_discount(self):
    #for record in self:
    #    compute actual discount from discount percentage
    #    discount = self.value * self.discount
    #    self.discount_value = discount
    #    self.total = self.value - discount

    
    #@api.one
    #@api.onchange('fieldx')
    #def do_stuff(self):
    #if self.fieldx == x:
    #  self.fieldy = 'toto'


    
    @api.one
    @api.depends('attribute', 'sale_line.product_template',
                 'sale_line.product_template.attribute_line_ids')
    def _get_possible_attribute_values(self): 
        attr_values = self.env['product.attribute.value']
        for attr_line in self.sale_line.product_template.attribute_line_ids:
            if attr_line.attribute_id.id == self.attribute.id:
                attr_values |= attr_line.value_ids
        self.possible_values = attr_values.sorted()

    sale_line = fields.Many2one(
        comodel_name='sale.order.line', string='Order line')
    attribute = fields.Many2one(
        comodel_name='product.attribute', string='Attributex')
    value = fields.Many2one(
        comodel_name='product.attribute.value', string='Value',
        domain="[('id', 'in', possible_values[0][2])]")
    possible_values = fields.Many2many(
        comodel_name='product.attribute.value',
        compute='_get_possible_attribute_values', readonly=True)
    mp_qty = fields.Float(compute='_get_qty', readonly=False, string='Cantidad', help="Cantidad de materia prima a Utilizar")
    price_extra = fields.Float(
        compute='_get_price_extra', readonly=False, string='Precio',
        digits=dp.get_precision('Product Price'),
        help="")
    size_x = fields.Float(digits=(16,2), string='Largo')
    size_y = fields.Float(digits=(16,2), string='Ancho/Alto')
    size_z = fields.Float(digits=(16,2), string='qty')

    



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_template = fields.Many2one(
        comodel_name='product.template', string='Product Template',
        readonly=False, states={'draft': [('readonly', False)],
                               'sent': [('readonly', False)]})
    product_attributes = fields.One2many(
        comodel_name='sale.order.line.attribute', inverse_name='sale_line',
        string='Product attributes', copy=True,
        readonly=False, states={'draft': [('readonly', False)],
                               'sent': [('readonly', False)]})
    # Neeeded because one2many result type is not constant when evaluating
    # visibility in XML
    product_attributes_count = fields.Integer(
        compute="_get_product_attributes_count")
    order_state = fields.Selection(related='order_id.state', readonly=False)
    product_id = fields.Many2one(
        domain="[('product_tmpl_id', '=', product_template)]")

    @api.one
    @api.depends('product_attributes')
    def _get_product_attributes_count(self):
        self.product_attributes_count = len(self.product_attributes)

    def _get_product_description(self, template, product, product_attributes):
        name = product and product.name or template.name
        group = self.env.ref(
            'sale_product_variants.group_product_variant_extended_description')
        extended = group in self.env.user.groups_id
        if not product_attributes and product:
            product_attributes = product.attribute_value_ids
        if extended:
            description = "\n".join(product_attributes.mapped(
                lambda x: "%s: %s" % (x.attribute_id.name, x.name)))
        else:
            description = ", ".join(product_attributes.mapped('name'))
        if not description:
            return name
        return ("%s\n%s" if extended else "%s (%s)") % (name, description)

    @api.multi
    def product_id_change(
            self, pricelist, product_id, qty=0, uom=False, qty_uos=0,
            uos=False, name='', partner_id=False, lang=False, update_tax=True,
            date_order=False, packaging=False, fiscal_position=False,
            flag=False):
        product_obj = self.env['product.product']
        res = super(SaleOrderLine, self).product_id_change(
            pricelist, product_id, qty=qty, uom=uom, qty_uos=qty_uos, uos=uos,
            name=name, partner_id=partner_id, lang=lang, update_tax=update_tax,
            date_order=date_order, packaging=packaging,
            fiscal_position=fiscal_position, flag=flag)
        if product_id:
            product = product_obj.browse(product_id)
            res['value']['product_attributes'] = (
                product._get_product_attributes_values_dict())
            res['value']['name'] = self._get_product_description(
                product.product_tmpl_id, product, product.attribute_value_ids)
        return res

    @api.multi
    @api.onchange('product_template')
    def onchange_product_template(self):
        self.ensure_one()
        self.name = self.product_template.name
        if not self.product_template.attribute_line_ids:
            self.product_id = (
                self.product_template.product_variant_ids and
                self.product_template.product_variant_ids[0])
        else:
            self.product_id = False
            self.product_uom = self.product_template.uom_id
            self.product_uos = self.product_template.uos_id
            self.price_unit = self.order_id.pricelist_id.with_context(
                {'uom': self.product_uom.id,
                 'date': self.order_id.date_order}).template_price_get(
                self.product_template.id, self.product_uom_qty or 1.0,
                self.order_id.partner_id.id)[self.order_id.pricelist_id.id]
        self.product_attributes = (
            self.product_template._get_product_attributes_dict())
        # Update taxes
        fpos = self.order_id.fiscal_position
        if not fpos:
            fpos = self.order_id.partner_id.property_account_position
        self.tax_id = fpos.map_tax(self.product_template.taxes_id)

    @api.one
    @api.onchange('product_attributes')
    def onchange_product_attributes(self):
        product_obj = self.env['product.product']
        self.product_id = product_obj._product_find(
            self.product_template, self.product_attributes)
        if not self.product_id:
            self.name = self._get_product_description(
                self.product_template, False,
                self.product_attributes.mapped('value'))
        if self.product_template:
            self.update_price_unit()

    @api.multi
    def action_duplicate(self):
        self.ensure_one()
        self.copy()
        # Force reload of the view as a workaround for lp:1155525
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'sale.order',
            'res_id': self.order_id.id,
            'type': 'ir.actions.act_window',
        }

    @api.one
    def _check_line_confirmability(self):
        if any(not bool(line.value) for line in self.product_attributes):
            raise exceptions.Warning(
                _("You can not confirm before configuring all attribute "
                  "values."))

    @api.multi
    def button_confirm(self):
        product_obj = self.env['product.product']
        for line in self:
            if not line.product_id:
                line._check_line_confirmability()
                attr_values = line.product_attributes.mapped('value')
                domain = [('product_tmpl_id', '=', line.product_template.id)]
                for attr_value in attr_values:
                    domain.append(('attribute_value_ids', '=', attr_value.id))
                products = product_obj.search(domain)
                # Filter the product with the exact number of attributes values
                product = False
                for prod in products:
                    if len(prod.attribute_value_ids) == len(attr_values):
                        product = prod
                        break
                if not product:
                    product = product_obj.create(
                        {'product_tmpl_id': line.product_template.id,
                         'attribute_value_ids': [(6, 0, attr_values.ids)]})
                line.write({'product_id': product.id})
        super(SaleOrderLine, self).button_confirm()

    @api.multi
    def update_price_unit(self):
        self.ensure_one()
        if not self.product_id:
            price_extra = 0.0
            for attr_line in self.product_attributes:
                price_extra += attr_line.price_extra
            self.price_unit = self.order_id.pricelist_id.with_context(
                {
                    'uom': self.product_uom.id,
                    'date': self.order_id.date_order,
                    'price_extra': price_extra,
                }).template_price_get(
                self.product_template.id, self.product_uom_qty or 1.0,
                self.order_id.partner_id.id)[self.order_id.pricelist_id.id]

    
