from odoo import models, fields, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    vehicle_number = fields.Char(string='Vehicle Number', tracking=True)

    state = fields.Selection(
        selection_add=[('to_approve', 'Waiting Approval'), ('sale',)],
        ondelete={'to_approve': 'set default'},
    )

    def action_confirm(self):
        if self.env.context.get('skip_approval'):
            return super().action_confirm()
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Only draft or sent quotations can be sent for approval.'))
            order.state = 'to_approve'
            order.message_post(body=_('Quotation sent for approval.'))
        return True

    def action_approve(self):
        for order in self:
            if order.state != 'to_approve':
                raise UserError(_('This order is not waiting for approval.'))
        self.write({'state': 'draft'})
        self.message_post(body=_('Approved by %s.', self.env.user.name))
        return self.with_context(skip_approval=True).action_confirm()

    def action_reject(self):
        self.write({'state': 'draft'})
        self.message_post(body=_('Rejected by %s.', self.env.user.name))
        return True
