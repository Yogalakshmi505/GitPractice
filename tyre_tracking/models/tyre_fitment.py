from odoo import api, fields, models

from .tyre_master import POSITIONS


class TyreFitment(models.Model):
    _name = 'tyre.fitment'
    _description = 'Tyre Fitment'
    _order = 'fitment_date desc, id desc'
    _rec_name = 'tyre_id'

    tyre_id = fields.Many2one('tyre.master', string='Tyre', required=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=True)
    position = fields.Selection(POSITIONS, string='Position', required=True)
    fitment_date = fields.Date(string='Fitment Date', default=fields.Date.context_today)
    odometer_at_fit = fields.Float(string='Odo at Fit')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for fit in records:
            # Remove the old tyre from that position, then fit the new one
            old = self.env['tyre.master'].search([
                ('vehicle_id', '=', fit.vehicle_id.id), ('position', '=', fit.position),
                ('id', '!=', fit.tyre_id.id)])
            old.write({'vehicle_id': False, 'position': False, 'state': 'stock'})
            fit.tyre_id.write({'vehicle_id': fit.vehicle_id.id, 'position': fit.position,
                               'state': 'active'})
        return records
