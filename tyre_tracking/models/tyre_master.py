from odoo import api, fields, models

POSITIONS = [
    ('FL', 'Front Left'), ('FR', 'Front Right'),
    ('RL', 'Rear Left'), ('RR', 'Rear Right'),
]


class TyreMaster(models.Model):
    _name = 'tyre.master'
    _description = 'Tyre Master'

    name = fields.Char(string='Serial No', required=True)
    brand = fields.Char(string='Brand')
    size = fields.Char(string='Size')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    position = fields.Selection(POSITIONS, string='Position')
    axle = fields.Selection([('front', 'Front axle'), ('rear', 'Rear axle')],
                            compute='_compute_axle', store=True)
    speed = fields.Float(string='Speed (km/h)')
    temperature = fields.Float(string='Temperature (°C)')
    odometer = fields.Float(string='Odometer (km)')
    wear_level = fields.Float(string='Wear %')
    state = fields.Selection([('stock', 'In Stock'), ('active', 'Fitted'), ('scrap', 'Scrap')],
                             default='stock', string='Status')
    condition = fields.Selection([('good', 'Good'), ('warning', 'Check soon'), ('replace', 'Replace')],
                                 compute='_compute_condition', store=True)
    fitment_ids = fields.One2many('tyre.fitment', 'tyre_id', string='Fitment history')

    _sql_constraints = [
        ('vehicle_position_uniq', 'unique(vehicle_id, position)',
         'This position on this vehicle already has a tyre.'),
    ]

    @api.depends('position')
    def _compute_axle(self):
        for tyre in self:
            tyre.axle = {'F': 'front', 'R': 'rear'}.get((tyre.position or ' ')[0], False)

    @api.depends('wear_level')
    def _compute_condition(self):
        for tyre in self:
            if tyre.wear_level >= 80:
                tyre.condition = 'replace'
            elif tyre.wear_level >= 60:
                tyre.condition = 'warning'
            else:
                tyre.condition = 'good'

    def action_scrap(self):
        self.write({'state': 'scrap', 'vehicle_id': False, 'position': False})

    def _tyre_info(self):
        self.ensure_one()
        return {
            'id': self.id,
            'position': self.position,
            'position_label': dict(POSITIONS).get(self.position, ''),
            'serial': self.name,
            'brand': self.brand or '',
            'size': self.size or '',
            'speed': self.speed,
            'temperature': self.temperature,
            'odometer': self.odometer,
            'wear': self.wear_level,
            'condition': self.condition,
        }

    @api.model
    def get_vehicle_tyres(self, vehicle_id):
        """JS: colour of every tyre on the vehicle picture."""
        tyres = self.search([('vehicle_id', '=', vehicle_id), ('state', '=', 'active')])
        return {t.position: {'id': t.id, 'serial': t.name, 'condition': t.condition} for t in tyres}

    @api.model
    def get_axle_details(self, vehicle_id, axle):
        """JS: tyre touch -> every tyre on that axle."""
        tyres = self.search([('vehicle_id', '=', vehicle_id), ('axle', '=', axle),
                             ('state', '=', 'active')], order='position')
        return [t._tyre_info() for t in tyres]
