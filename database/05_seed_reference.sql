/* =====================================================================================
   05_seed_reference.sql - reference & master data
   * Chart of accounts and P&L layout are generated from the legacy P&L workbook
     ('Expense Category', 'Revenue Category', 'Profit and Loss' layout).
   * Prices, rates and fees are ILLUSTRATIVE values for the public demo, not AMI's real figures.
   ===================================================================================== */

-- Programmes & delivery modes -------------------------------------------------------
insert into ref.programme (programme_code, name, description) values
  ('AE',    'Applied English',   'CEFR-aligned English for primary and secondary students (Root, Trunk, Leaf, Flower; Starter ... Mastery)'),
  ('COMM',  'Communication',     'Speaking-focused courses for teenagers and adults'),
  ('IELTS', 'IELTS',             'IELTS preparation from 4.0+ to 7.0+'),
  ('PE',    'Practical English', 'Grade-based school-curriculum support, billed monthly');

insert into ref.delivery_mode (delivery_mode_code, name) values
  ('OFFLINE', 'Offline (classroom)'), ('ONLINE', 'Online'), ('CUSTOM', 'Customised 1:1'), ('CUSTOM_ONLINE', 'Customised 1:1 online');

insert into ref.app_setting (setting_key, setting_value, description) values
  ('as_of_date', null, 'Reporting reference date for status/ageing views; NULL = today (legacy TODAY())'),
  ('no_invoice_threshold', '200000', 'Payments without a VAT invoice at or above this amount are flagged by control EXP-01'),
  ('class_notice_days', '10', 'Days before start when a class shows "Starts in N days" (legacy rule)'),
  ('class_ending_days', '20', 'Days before end when a class shows "Ends in N days" (legacy rule)'),
  ('discount_approval_threshold', '0.30', 'Total discount above this share of list price needs Finance approval'),
  ('dropout_payment_policy', 'FORFEIT', 'FORFEIT: payments kept after a drop-out or cancellation are earned at once; REFUND: they stay deferred until Finance refunds them'),
  ('centre_name', 'AMI Education', 'Name printed on receipts and payslips'),
  ('centre_address', 'Demo campus, Bac Lieu, Viet Nam', 'Address printed on receipts and payslips');

-- Chart of accounts ---------------------------------------------------------------
insert into finance.gl_account (account_code, name, account_class, parent_account_code, is_postable, is_capex, is_depreciation, legacy_source, sort_order) values
  ('I1.001', 'Tuition revenue by product line', 'REVENUE', NULL, false, false, false, 'Revenue Category', 10),
  ('I1.0011', 'Applied English (offline)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: AE', 20),
  ('I1.0012', 'Communication (offline)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: COMM', 30),
  ('I1.0013', 'IELTS (offline)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: IELTS', 40),
  ('I1.0014', 'Applied English (online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: ONL AE', 50),
  ('I1.0015', 'Communication (online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: ONL COMM', 60),
  ('I1.0016', 'IELTS (online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: ONL IELTS', 70),
  ('I1.0017', 'Applied English (customised 1:1)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS AE', 80),
  ('I1.0018', 'Communication (customised 1:1)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS COMM', 90),
  ('I1.0019', 'IELTS (customised 1:1)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS IELTS', 100),
  ('I1.00110', 'Applied English (customised online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS ONL AE', 110),
  ('I1.00111', 'Communication (customised online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS ONL COMM', 120),
  ('I1.00112', 'IELTS (customised online)', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: CUS ONL IELTS', 130),
  ('I1.00113', 'Practical English', 'REVENUE', 'I1.001', true, false, false, 'Revenue Category: PE', 140),
  ('E0.001', 'Refunds & discounts', 'CONTRA_REVENUE', NULL, true, false, false, 'Expense Category', 150),
  ('E1.001', 'Teachers salaries', 'EXPENSE', NULL, false, false, false, 'Expense Category', 160),
  ('E1.0011', 'Teachers salaries - Applied English (offline)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 170),
  ('E1.0012', 'Teachers salaries - Communication (offline)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 180),
  ('E1.0013', 'Teachers salaries - IELTS (offline)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 190),
  ('E1.0014', 'Teachers salaries - Applied English (online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 200),
  ('E1.0015', 'Teachers salaries - Communication (online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 210),
  ('E1.0016', 'Teachers salaries - IELTS (online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 220),
  ('E1.0017', 'Teachers salaries - Applied English (customised 1:1)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 230),
  ('E1.0018', 'Teachers salaries - Communication (customised 1:1)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 240),
  ('E1.0019', 'Teachers salaries - IELTS (customised 1:1)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 250),
  ('E1.00110', 'Teachers salaries - Applied English (customised online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 260),
  ('E1.00111', 'Teachers salaries - Communication (customised online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 270),
  ('E1.00112', 'Teachers salaries - IELTS (customised online)', 'EXPENSE', 'E1.001', true, false, false, 'Expense Category', 280),
  ('E1.002', 'TA/AT salaries', 'EXPENSE', NULL, false, false, false, 'Expense Category', 290),
  ('E1.0021', 'TA/AT salaries - Applied English (offline)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 300),
  ('E1.0022', 'TA/AT salaries - Communication (offline)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 310),
  ('E1.0023', 'TA/AT salaries - IELTS (offline)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 320),
  ('E1.0024', 'TA/AT salaries - Applied English (online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 330),
  ('E1.0025', 'TA/AT salaries - Communication (online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 340),
  ('E1.0026', 'TA/AT salaries - IELTS (online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 350),
  ('E1.0027', 'TA/AT salaries - Applied English (customised 1:1)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 360),
  ('E1.0028', 'TA/AT salaries - Communication (customised 1:1)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 370),
  ('E1.0029', 'TA/AT salaries - IELTS (customised 1:1)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 380),
  ('E1.00210', 'TA/AT salaries - Applied English (customised online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 390),
  ('E1.00211', 'TA/AT salaries - Communication (customised online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 400),
  ('E1.00212', 'TA/AT salaries - IELTS (customised online)', 'EXPENSE', 'E1.002', true, false, false, 'Expense Category', 410),
  ('E1.003', 'Variable salaries - Executive level (LA,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 420),
  ('E1.004', 'Fixed salaries - Executive level', 'EXPENSE', NULL, true, false, false, 'Expense Category', 430),
  ('E1.005', 'Fixed salaries - Executive level (MKT,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 440),
  ('E1.006', 'Expats salaries', 'EXPENSE', NULL, false, false, false, 'Expense Category', 450),
  ('E1.0061', 'Expats salaries - Applied English (offline)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 460),
  ('E1.0062', 'Expats salaries - Communication (offline)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 470),
  ('E1.0063', 'Expats salaries - IELTS (offline)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 480),
  ('E1.0064', 'Expats salaries - Applied English (online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 490),
  ('E1.0065', 'Expats salaries - Communication (online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 500),
  ('E1.0066', 'Expats salaries - IELTS (online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 510),
  ('E1.0067', 'Expats salaries - Applied English (customised 1:1)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 520),
  ('E1.0068', 'Expats salaries - Communication (customised 1:1)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 530),
  ('E1.0069', 'Expats salaries - IELTS (customised 1:1)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 540),
  ('E1.00610', 'Expats salaries - Applied English (customised online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 550),
  ('E1.00611', 'Expats salaries - Communication (customised online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 560),
  ('E1.00612', 'Expats salaries - IELTS (customised online)', 'EXPENSE', 'E1.006', true, false, false, 'Expense Category', 570),
  ('E1.007', 'Social Insurance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 580),
  ('E1.008', 'Health Insurance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 590),
  ('E1.009', 'Union fee', 'EXPENSE', NULL, true, false, false, 'Expense Category', 600),
  ('E1.010', 'Performance bonus', 'EXPENSE', NULL, true, false, false, 'Expense Category', 610),
  ('E1.011', 'Overtime', 'EXPENSE', NULL, true, false, false, 'Expense Category', 620),
  ('E1.012', 'End of contract', 'EXPENSE', NULL, true, false, false, 'Expense Category', 630),
  ('E1.013', 'Other benefits', 'EXPENSE', NULL, true, false, false, 'Expense Category', 640),
  ('E1.014', 'Other income', 'EXPENSE', NULL, true, false, false, 'Expense Category', 650),
  ('E1.015', 'Unemployment insurance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 660),
  ('E1.016', 'Non-teaching activities', 'EXPENSE', NULL, true, false, false, 'Expense Category', 670),
  ('E1.017', 'Placement test', 'EXPENSE', NULL, true, false, false, 'Expense Category', 680),
  ('E1.018', 'Online learning', 'EXPENSE', NULL, true, false, false, 'Expense Category', 690),
  ('E1.019', 'Service contract', 'EXPENSE', NULL, true, false, false, 'Expense Category', 700),
  ('E1.020', 'Fixed salaries - Management level (CEN, LAM,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 710),
  ('E1.021', 'Fixed salaries - Management level', 'EXPENSE', NULL, true, false, false, 'Expense Category', 720),
  ('E2.001', 'Paper', 'EXPENSE', NULL, true, false, false, 'Expense Category', 730),
  ('E2.002', 'Stationery', 'EXPENSE', NULL, true, false, false, 'Expense Category', 740),
  ('E3.001', 'IT equipments', 'EXPENSE', NULL, true, true, false, 'Expense Category', 750),
  ('E3.002', 'Office Tools & Equipment', 'EXPENSE', NULL, true, true, false, 'Expense Category', 760),
  ('E3.003', 'Fit-out/Renovation', 'EXPENSE', NULL, true, true, false, 'Expense Category', 770),
  ('E3.004', 'IT equipments - Allocation', 'EXPENSE', NULL, true, false, true, 'Expense Category', 780),
  ('E3.005', 'Office Tools & Equipment - Allocation', 'EXPENSE', NULL, true, false, true, 'Expense Category', 790),
  ('E3.006', 'Fit-out/Renovation - Allocation', 'EXPENSE', NULL, true, false, true, 'Expense Category', 800),
  ('E4.001', 'Depreciation', 'EXPENSE', NULL, true, false, true, 'Expense Category', 810),
  ('E5.001', 'Cambridge service costs', 'EXPENSE', NULL, true, false, false, 'Expense Category', 820),
  ('E5.002', 'Outsourcing services', 'EXPENSE', NULL, true, false, false, 'Expense Category', 830),
  ('E6.001', 'Bad Debts', 'EXPENSE', NULL, true, false, false, 'Expense Category', 840),
  ('E7.001', 'Audit Fees', 'EXPENSE', NULL, true, false, false, 'Expense Category', 850),
  ('E7.002', 'Recruitment fee for Academic staff', 'EXPENSE', NULL, true, false, false, 'Expense Category', 860),
  ('E7.003', 'Recruitment fee for Admin staff', 'EXPENSE', NULL, true, false, false, 'Expense Category', 870),
  ('E7.004', 'Consultant fee', 'EXPENSE', NULL, true, false, false, 'Expense Category', 880),
  ('E7.005', 'IT Repairs & Maintenance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 890),
  ('E7.006', 'Office Repairs & Maintenance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 900),
  ('E7.007', 'Heat, Light & Power (including: utilities, power, water...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 910),
  ('E7.008', 'Telephone/fax', 'EXPENSE', NULL, true, false, false, 'Expense Category', 920),
  ('E7.009', 'Postage', 'EXPENSE', NULL, true, false, false, 'Expense Category', 930),
  ('E7.010', 'Insurance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 940),
  ('E7.011', 'Bank & Credit Card Charges', 'EXPENSE', NULL, true, false, false, 'Expense Category', 950),
  ('E7.012', 'Office rent', 'EXPENSE', NULL, true, false, false, 'Expense Category', 960),
  ('E7.013', 'Equipment hire and its maintenance (photocopiers, other equipments)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 970),
  ('E7.014', 'Other Rental Expenses (Parking/Others)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 980),
  ('E7.015', 'Cleaning', 'EXPENSE', NULL, true, false, false, 'Expense Category', 990),
  ('E7.016', 'Internet/ADSL & Communication line', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1000),
  ('E7.017', 'Security Fee', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1010),
  ('E7.023', 'IT outsourcing services', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1020),
  ('E8.001', 'Materials for Students', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1030),
  ('E8.002', 'Travel (taxi, car rental)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1040),
  ('E8.003', 'Business trip (air ticket, perdiem, hotel, visa, transportation...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1050),
  ('E8.004', 'Payments for TT/OSC (salary, air ticket, accommodation,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1060),
  ('E8.005', 'Photocopy expense', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1070),
  ('E8.006', 'Printing (Letter head, name card, envelop, report book,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1080),
  ('E8.007', 'Subscriptions', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1090),
  ('E8.008', 'Class activities', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1100),
  ('E8.009', 'Teaching Resources', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1110),
  ('E8.010', 'Entertaining', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1120),
  ('E8.011', 'Refreshment for staffs', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1130),
  ('E8.012', 'Internal Rewards & Appreciation', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1140),
  ('E8.013', 'Staff Training', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1150),
  ('E8.014', 'Meeting expense', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1160),
  ('E8.015', 'Sponsor, Donation, Gift', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1170),
  ('E8.016', 'Miscellaneous expenses', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1180),
  ('E8.017', 'Mobile phone allowance', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1190),
  ('E8.018', 'PR-Newspaper', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1200),
  ('E8.019', 'Events/Activations/Seminars', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1210),
  ('E8.020', 'Production (Giftset,Creative,TVC, clips,flyer, standee, brochure,.....)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1220),
  ('E8.021', 'Print Ads', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1230),
  ('E8.022', 'Promotion - New sales & Re-enrolment', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1240),
  ('E8.023', 'TVC - Clips', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1250),
  ('E8.024', 'Street banner - New visibility platform (taxi, digital frame,...)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1260),
  ('E8.025', 'Sponsorship/Media relation', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1270),
  ('E8.026', 'Promotion - Re-enrollment', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1280),
  ('E8.027', 'Local Events (Fun Day + Open Day)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1290),
  ('E8.028', 'Activation-re-enroll', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1300),
  ('E8.029', 'Engagement activities (Annual outing trip)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1310),
  ('E8.030', 'Company/School co-operation', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1320),
  ('E8.031', 'VAT deductible', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1330),
  ('E8.032', 'Teacher Training', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1340),
  ('E8.033', 'PR (online, print ads, newspaper)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1350),
  ('E8.034', 'Apps-Mobile-SMS-E-mail', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1360),
  ('E8.035', 'Website (Design, Domain, censorship)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1370),
  ('E8.036', 'Digital (online ads - FB, Google, Pages, Forum....)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1380),
  ('E8.037', 'Market Research/Brand Health Tracking', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1390),
  ('E8.038', 'Agency fee', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1400),
  ('E8.039', 'Fan Page Management', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1410),
  ('E8.040', 'Social (forum & social seeding / feeding, KOLs)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1420),
  ('E8.041', 'Viral/Content MRK (youtube-FB)', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1430),
  ('E8.042', 'New centre launch', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1440),
  ('E8.043', 'OOH - Local billboard - Public billboard - Center Decoration', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1450),
  ('E8.044', 'Enrichment', 'EXPENSE', NULL, true, false, false, 'Expense Category', 1460),
  ('B1.001', 'Cash on hand', 'ASSET', NULL, true, false, false, 'Added in the relational model (journals)', 1470),
  ('B1.002', 'Bank account', 'ASSET', NULL, true, false, false, 'Added in the relational model (journals)', 1480),
  ('B1.101', 'Tuition receivable', 'ASSET', NULL, true, false, false, 'Added in the relational model (journals)', 1490),
  ('B1.201', 'Fixed assets - cost', 'ASSET', NULL, true, false, false, 'Added in the relational model (journals)', 1500),
  ('B1.202', 'Accumulated depreciation', 'ASSET', NULL, true, false, false, 'Added in the relational model (journals)', 1510),
  ('B2.001', 'Deferred tuition revenue', 'LIABILITY', NULL, true, false, false, 'Added in the relational model (journals)', 1520),
  ('B2.101', 'Salaries payable', 'LIABILITY', NULL, true, false, false, 'Added in the relational model (journals)', 1530),
  ('B2.102', 'PIT withheld payable', 'LIABILITY', NULL, true, false, false, 'Added in the relational model (journals)', 1540),
  ('B2.201', 'Accrued expenses', 'LIABILITY', NULL, true, false, false, 'Added in the relational model (journals)', 1550),
  ('B3.001', 'Owners'' capital', 'EQUITY', NULL, true, false, false, 'Added in the relational model (journals)', 1560),
  ('B3.002', 'Retained earnings', 'EQUITY', NULL, true, false, false, 'Added in the relational model (journals)', 1570);

-- P&L layout ----------------------------------------------------------------------
insert into finance.pnl_line (pnl_line_code, name, section, subsection, legacy_line_code, sort_order) values
  ('REV-01', 'Applied English', 'REVENUE', NULL, NULL, 10),
  ('REV-02', 'Communication', 'REVENUE', NULL, NULL, 20),
  ('REV-03', 'IELTS', 'REVENUE', NULL, NULL, 30),
  ('REV-04', 'Practical English', 'REVENUE', NULL, NULL, 40),
  ('DED-01', 'Refunds & discounts', 'REVENUE_DEDUCTIONS', NULL, NULL, 50),
  ('COS-01', 'Teachers salaries', 'COST_OF_SALES', 'Teaching cost', 'DC01', 60),
  ('COS-02', 'Union fee', 'COST_OF_SALES', 'Teaching cost', NULL, 70),
  ('COS-03', 'Social Insurance', 'COST_OF_SALES', 'Teaching cost', NULL, 80),
  ('COS-04', 'Health Insurance', 'COST_OF_SALES', 'Teaching cost', 'DC02', 90),
  ('COS-05', 'End of contract', 'COST_OF_SALES', 'Teaching cost', 'DC03', 100),
  ('COS-06', 'Expats salaries', 'COST_OF_SALES', 'Teaching cost', 'DC16', 110),
  ('COS-07', 'Payments for TT/OSC (salary, air ticket, accommodation,...)', 'COST_OF_SALES', 'Teaching cost', 'DC04', 120),
  ('COS-08', 'Overtime', 'COST_OF_SALES', 'Teaching cost', 'DC05', 130),
  ('COS-09', 'Teacher Training', 'COST_OF_SALES', 'Teaching cost', 'DC21', 140),
  ('COS-10', 'Engagement activities (Annual outing trip)', 'COST_OF_SALES', 'Teaching cost', NULL, 150),
  ('COS-11', 'Placement test', 'COST_OF_SALES', 'Teaching cost', 'DC07', 160),
  ('COS-12', 'TA/AT cost', 'COST_OF_SALES', 'Teaching cost', NULL, 170),
  ('COS-13', 'Fixed salaries - Executive level', 'COST_OF_SALES', 'Non-teaching cost', NULL, 180),
  ('COS-14', 'Fixed salaries - Management level', 'COST_OF_SALES', 'Non-teaching cost', NULL, 190),
  ('COS-15', 'Non-teaching activities', 'COST_OF_SALES', 'Non-teaching cost', NULL, 200),
  ('COS-16', 'Materials for Students', 'COST_OF_SALES', 'Program & Delivery Costs', 'P01', 210),
  ('COS-17', 'Cambridge service costs', 'COST_OF_SALES', 'Program & Delivery Costs', 'DC12', 220),
  ('COS-18', 'Company/School co-operation', 'COST_OF_SALES', 'Program & Delivery Costs', 'AC33', 230),
  ('COS-19', 'Enrichment', 'COST_OF_SALES', 'Program & Delivery Costs', 'DC22', 240),
  ('COS-20', 'Outsourcing services', 'COST_OF_SALES', 'Program & Delivery Costs', 'DC17', 250),
  ('COS-21', 'Online learning', 'COST_OF_SALES', 'Program & Delivery Costs', 'DC17', 260),
  ('STF-01', 'Variable salaries - Executive level (LA,...)', 'STAFF_COSTS', 'Variable salaries', 'SA01', 270),
  ('STF-02', 'Fixed salaries - Executive level (MKT,...)', 'STAFF_COSTS', 'Fixed salaries', NULL, 280),
  ('STF-03', 'Fixed salaries - Management level (CEN, LAM,...)', 'STAFF_COSTS', 'Fixed salaries', NULL, 290),
  ('STF-04', 'Union fee', 'STAFF_COSTS', 'Other staff costs', 'SA20', 300),
  ('STF-05', 'Social Insurance', 'STAFF_COSTS', 'Other staff costs', 'SA02', 310),
  ('STF-06', 'Health Insurance', 'STAFF_COSTS', 'Other staff costs', 'SA03', 320),
  ('STF-07', 'Unemployment insurance', 'STAFF_COSTS', 'Other staff costs', 'SA04', 330),
  ('STF-08', 'Performance bonus', 'STAFF_COSTS', 'Other staff costs', 'SA06', 340),
  ('STF-09', 'End of contract', 'STAFF_COSTS', 'Other staff costs', 'SA07', 350),
  ('STF-10', 'Other income', 'STAFF_COSTS', 'Other staff costs', 'SA09', 360),
  ('STF-11', 'Mobile phone allowance', 'STAFF_COSTS', 'Other staff costs', NULL, 370),
  ('STF-12', 'Engagement activities (Annual outing trip)', 'STAFF_COSTS', 'Benefits in kind', 'SA12', 380),
  ('STF-13', 'Other benefits', 'STAFF_COSTS', 'Benefits in kind', 'SA19', 390),
  ('STF-14', 'Staff Training', 'STAFF_COSTS', 'Benefits in kind', 'ST01', 400),
  ('STF-15', 'Recruitment fee for Academic staff', 'STAFF_COSTS', 'Staff Recruitment', 'SR01', 410),
  ('STF-16', 'Recruitment fee for Admin staff', 'STAFF_COSTS', 'Staff Recruitment', 'SR02', 420),
  ('STF-17', 'Service contract', 'STAFF_COSTS', 'Staff Recruitment', 'SA21', 430),
  ('MKT-01', 'PR-Newspaper', 'MARKETING_COSTS', 'CAMPAIGN', 'DA02', 440),
  ('MKT-02', 'Events/Activations/Seminars', 'MARKETING_COSTS', 'CAMPAIGN', 'DA03', 450),
  ('MKT-03', 'Print Ads', 'MARKETING_COSTS', 'CAMPAIGN', 'DA06', 460),
  ('MKT-04', 'TVC - Clips', 'MARKETING_COSTS', 'CAMPAIGN', 'DA09', 470),
  ('MKT-05', 'Street banner - New visibility platform (taxi, digital frame,...)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA12', 480),
  ('MKT-06', 'Sponsorship/Media relation', 'MARKETING_COSTS', 'CAMPAIGN', 'DA14', 490),
  ('MKT-07', 'Activation-re-enroll', 'MARKETING_COSTS', 'CAMPAIGN', 'DA26', 500),
  ('MKT-08', 'New centre launch', 'MARKETING_COSTS', 'CAMPAIGN', 'DA27', 510),
  ('MKT-09', 'PR (online, print ads, newspaper)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA20', 520),
  ('MKT-10', 'Apps-Mobile-SMS-E-mail', 'MARKETING_COSTS', 'CAMPAIGN', 'DA21', 530),
  ('MKT-11', 'Website (Design, Domain, censorship)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA23', 540),
  ('MKT-12', 'Digital (online ads - FB, Google, Pages, Forum....)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA24', 550),
  ('MKT-13', 'Fan Page Management', 'MARKETING_COSTS', 'CAMPAIGN', 'DA28', 560),
  ('MKT-14', 'Social (forum & social seeding / feeding, KOLs)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA29', 570),
  ('MKT-15', 'Viral/Content MRK (youtube-FB)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA30', 580),
  ('MKT-16', 'Production (Giftset,Creative,TVC, clips,flyer, standee, brochure,.....)', 'MARKETING_COSTS', 'CAMPAIGN', 'DA05', 590),
  ('MKT-17', 'Market Research/Brand Health Tracking', 'MARKETING_COSTS', 'CAMPAIGN', 'DA31', 600),
  ('MKT-18', 'Agency fee', 'MARKETING_COSTS', 'CAMPAIGN', 'DA32', 610),
  ('MKT-19', 'Promotion - New sales & Re-enrolment', 'MARKETING_COSTS', 'FIXED COST', 'DA08', 620),
  ('MKT-20', 'Promotion - Re-enrollment', 'MARKETING_COSTS', 'FIXED COST', 'DA16', 630),
  ('MKT-21', 'OOH - Local billboard - Public billboard - Center Decoration', 'MARKETING_COSTS', 'FIXED COST', 'DA33', 640),
  ('MKT-22', 'Local Events (Fun Day + Open Day)', 'MARKETING_COSTS', 'LOCAL MRK', 'DA17', 650),
  ('EST-01', 'Depreciation', 'ESTABLISHMENT_COSTS', NULL, 'EC01', 660),
  ('EST-02', 'Office rent', 'ESTABLISHMENT_COSTS', NULL, 'EC02', 670),
  ('EST-03', 'Heat, Light & Power (including: utilities, power, water...)', 'ESTABLISHMENT_COSTS', NULL, 'EC03', 680),
  ('EST-04', 'Insurance', 'ESTABLISHMENT_COSTS', NULL, 'EC04', 690),
  ('EST-05', 'IT equipments - Allocation', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'AC34', 700),
  ('EST-06', 'IT Repairs & Maintenance', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'EC05', 710),
  ('EST-07', 'IT outsourcing services', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'EC08', 720),
  ('EST-08', 'Office Tools & Equipment - Allocation', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'AC35', 730),
  ('EST-09', 'Fit-out/Renovation - Allocation', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'AC36', 740),
  ('EST-10', 'Office Repairs & Maintenance', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'EC06', 750),
  ('EST-11', 'Cleaning', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'EC07', 760),
  ('EST-12', 'Security Fee', 'ESTABLISHMENT_COSTS', 'IT & Related costs', 'AC30', 770),
  ('ADM-01', 'Class activities', 'ADMINISTRATION_COSTS', NULL, 'AC01', 780),
  ('ADM-02', 'Refreshment for staffs', 'ADMINISTRATION_COSTS', NULL, 'AC02', 790),
  ('ADM-03', 'Travel (taxi, car rental)', 'ADMINISTRATION_COSTS', 'Travel and subsistence', 'AC04', 800),
  ('ADM-04', 'Business trip (air ticket, perdiem, hotel, visa, transportation...)', 'ADMINISTRATION_COSTS', 'Travel and subsistence', 'AC05', 810),
  ('ADM-05', 'Entertaining', 'ADMINISTRATION_COSTS', 'Travel and subsistence', 'AC06', 820),
  ('ADM-06', 'Telephone/fax', 'ADMINISTRATION_COSTS', 'Telephones / Fax / Internet', 'AC07', 830),
  ('ADM-07', 'Internet/ADSL & Communication line', 'ADMINISTRATION_COSTS', 'Telephones / Fax / Internet', 'AC08', 840),
  ('ADM-08', 'Paper', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC09', 850),
  ('ADM-09', 'Stationery', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC10', 860),
  ('ADM-10', 'Printing (Letter head, name card, envelop, report book,...)', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC11', 870),
  ('ADM-11', 'Teaching Resources', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC12', 880),
  ('ADM-12', 'Photocopy expense', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC13', 890),
  ('ADM-13', 'Postage', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC14', 900),
  ('ADM-14', 'Audit Fees', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC16', 910),
  ('ADM-15', 'Consultant fee', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC17', 920),
  ('ADM-16', 'Subscriptions', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC18', 930),
  ('ADM-17', 'Equipment hire and its maintenance (photocopiers, other equipments)', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC19', 940),
  ('ADM-18', 'Bank & Credit Card Charges', 'ADMINISTRATION_COSTS', 'Stationery / Printing', 'AC23', 950),
  ('ADM-19', 'Other Rental Expenses (Parking/Others)', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC24', 960),
  ('ADM-20', 'Sponsor, Donation, Gift', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC25', 970),
  ('ADM-21', 'Internal Rewards & Appreciation', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC26', 980),
  ('ADM-22', 'Meeting expense', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC28', 990),
  ('ADM-23', 'Bad Debts', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC29', 1000),
  ('ADM-24', 'VAT deductible', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC37', 1010),
  ('ADM-25', 'Miscellaneous expenses', 'ADMINISTRATION_COSTS', 'Sundry Costs', 'AC31', 1020);

insert into finance.pnl_line_mapping (account_code, cost_center_scope, pnl_line_code) values
  ('I1.0011', 'ANY', 'REV-01'),
  ('I1.0014', 'ANY', 'REV-01'),
  ('I1.0017', 'ANY', 'REV-01'),
  ('I1.00110', 'ANY', 'REV-01'),
  ('I1.0012', 'ANY', 'REV-02'),
  ('I1.0015', 'ANY', 'REV-02'),
  ('I1.0018', 'ANY', 'REV-02'),
  ('I1.00111', 'ANY', 'REV-02'),
  ('I1.0013', 'ANY', 'REV-03'),
  ('I1.0016', 'ANY', 'REV-03'),
  ('I1.0019', 'ANY', 'REV-03'),
  ('I1.00112', 'ANY', 'REV-03'),
  ('I1.00113', 'ANY', 'REV-04'),
  ('E0.001', 'ANY', 'DED-01'),
  ('E1.0011', 'ANY', 'COS-01'),
  ('E1.0012', 'ANY', 'COS-01'),
  ('E1.0013', 'ANY', 'COS-01'),
  ('E1.0014', 'ANY', 'COS-01'),
  ('E1.0015', 'ANY', 'COS-01'),
  ('E1.0016', 'ANY', 'COS-01'),
  ('E1.0017', 'ANY', 'COS-01'),
  ('E1.0018', 'ANY', 'COS-01'),
  ('E1.0019', 'ANY', 'COS-01'),
  ('E1.00110', 'ANY', 'COS-01'),
  ('E1.00111', 'ANY', 'COS-01'),
  ('E1.00112', 'ANY', 'COS-01'),
  ('E1.009', 'ACADEMIC', 'COS-02'),
  ('E1.007', 'ACADEMIC', 'COS-03'),
  ('E1.008', 'ACADEMIC', 'COS-04'),
  ('E1.012', 'ACADEMIC', 'COS-05'),
  ('E1.0061', 'ANY', 'COS-06'),
  ('E1.0062', 'ANY', 'COS-06'),
  ('E1.0063', 'ANY', 'COS-06'),
  ('E1.0064', 'ANY', 'COS-06'),
  ('E1.0065', 'ANY', 'COS-06'),
  ('E1.0066', 'ANY', 'COS-06'),
  ('E1.0067', 'ANY', 'COS-06'),
  ('E1.0068', 'ANY', 'COS-06'),
  ('E1.0069', 'ANY', 'COS-06'),
  ('E1.00610', 'ANY', 'COS-06'),
  ('E1.00611', 'ANY', 'COS-06'),
  ('E1.00612', 'ANY', 'COS-06'),
  ('E8.004', 'ANY', 'COS-07'),
  ('E1.011', 'ANY', 'COS-08'),
  ('E8.032', 'ANY', 'COS-09'),
  ('E8.029', 'ACADEMIC', 'COS-10'),
  ('E1.017', 'ANY', 'COS-11'),
  ('E1.0021', 'ANY', 'COS-12'),
  ('E1.0022', 'ANY', 'COS-12'),
  ('E1.0023', 'ANY', 'COS-12'),
  ('E1.0024', 'ANY', 'COS-12'),
  ('E1.0025', 'ANY', 'COS-12'),
  ('E1.0026', 'ANY', 'COS-12'),
  ('E1.0027', 'ANY', 'COS-12'),
  ('E1.0028', 'ANY', 'COS-12'),
  ('E1.0029', 'ANY', 'COS-12'),
  ('E1.00210', 'ANY', 'COS-12'),
  ('E1.00211', 'ANY', 'COS-12'),
  ('E1.00212', 'ANY', 'COS-12'),
  ('E1.004', 'ANY', 'COS-13'),
  ('E1.021', 'ANY', 'COS-14'),
  ('E1.016', 'ANY', 'COS-15'),
  ('E8.001', 'ANY', 'COS-16'),
  ('E5.001', 'ANY', 'COS-17'),
  ('E8.030', 'ANY', 'COS-18'),
  ('E8.044', 'ANY', 'COS-19'),
  ('E5.002', 'ANY', 'COS-20'),
  ('E1.018', 'ANY', 'COS-21'),
  ('E1.003', 'ANY', 'STF-01'),
  ('E1.005', 'ANY', 'STF-02'),
  ('E1.020', 'ANY', 'STF-03'),
  ('E1.009', 'NON_ACADEMIC', 'STF-04'),
  ('E1.007', 'NON_ACADEMIC', 'STF-05'),
  ('E1.008', 'NON_ACADEMIC', 'STF-06'),
  ('E1.015', 'ANY', 'STF-07'),
  ('E1.010', 'ANY', 'STF-08'),
  ('E1.012', 'NON_ACADEMIC', 'STF-09'),
  ('E1.014', 'ANY', 'STF-10'),
  ('E8.017', 'ANY', 'STF-11'),
  ('E8.029', 'NON_ACADEMIC', 'STF-12'),
  ('E1.013', 'ANY', 'STF-13'),
  ('E8.013', 'ANY', 'STF-14'),
  ('E7.002', 'ANY', 'STF-15'),
  ('E7.003', 'ANY', 'STF-16'),
  ('E1.019', 'ANY', 'STF-17'),
  ('E8.018', 'ANY', 'MKT-01'),
  ('E8.019', 'ANY', 'MKT-02'),
  ('E8.021', 'ANY', 'MKT-03'),
  ('E8.023', 'ANY', 'MKT-04'),
  ('E8.024', 'ANY', 'MKT-05'),
  ('E8.025', 'ANY', 'MKT-06'),
  ('E8.028', 'ANY', 'MKT-07'),
  ('E8.042', 'ANY', 'MKT-08'),
  ('E8.033', 'ANY', 'MKT-09'),
  ('E8.034', 'ANY', 'MKT-10'),
  ('E8.035', 'ANY', 'MKT-11'),
  ('E8.036', 'ANY', 'MKT-12'),
  ('E8.039', 'ANY', 'MKT-13'),
  ('E8.040', 'ANY', 'MKT-14'),
  ('E8.041', 'ANY', 'MKT-15'),
  ('E8.020', 'ANY', 'MKT-16'),
  ('E8.037', 'ANY', 'MKT-17'),
  ('E8.038', 'ANY', 'MKT-18'),
  ('E8.022', 'ANY', 'MKT-19'),
  ('E8.026', 'ANY', 'MKT-20'),
  ('E8.043', 'ANY', 'MKT-21'),
  ('E8.027', 'ANY', 'MKT-22'),
  ('E4.001', 'ANY', 'EST-01'),
  ('E7.012', 'ANY', 'EST-02'),
  ('E7.007', 'ANY', 'EST-03'),
  ('E7.010', 'ANY', 'EST-04'),
  ('E3.004', 'ANY', 'EST-05'),
  ('E7.005', 'ANY', 'EST-06'),
  ('E7.023', 'ANY', 'EST-07'),
  ('E3.005', 'ANY', 'EST-08'),
  ('E3.006', 'ANY', 'EST-09'),
  ('E7.006', 'ANY', 'EST-10'),
  ('E7.015', 'ANY', 'EST-11'),
  ('E7.017', 'ANY', 'EST-12'),
  ('E8.008', 'ANY', 'ADM-01'),
  ('E8.011', 'ANY', 'ADM-02'),
  ('E8.002', 'ANY', 'ADM-03'),
  ('E8.003', 'ANY', 'ADM-04'),
  ('E8.010', 'ANY', 'ADM-05'),
  ('E7.008', 'ANY', 'ADM-06'),
  ('E7.016', 'ANY', 'ADM-07'),
  ('E2.001', 'ANY', 'ADM-08'),
  ('E2.002', 'ANY', 'ADM-09'),
  ('E8.006', 'ANY', 'ADM-10'),
  ('E8.009', 'ANY', 'ADM-11'),
  ('E8.005', 'ANY', 'ADM-12'),
  ('E7.009', 'ANY', 'ADM-13'),
  ('E7.001', 'ANY', 'ADM-14'),
  ('E7.004', 'ANY', 'ADM-15'),
  ('E8.007', 'ANY', 'ADM-16'),
  ('E7.013', 'ANY', 'ADM-17'),
  ('E7.011', 'ANY', 'ADM-18'),
  ('E7.014', 'ANY', 'ADM-19'),
  ('E8.015', 'ANY', 'ADM-20'),
  ('E8.012', 'ANY', 'ADM-21'),
  ('E8.014', 'ANY', 'ADM-22'),
  ('E6.001', 'ANY', 'ADM-23'),
  ('E8.031', 'ANY', 'ADM-24'),
  ('E8.016', 'ANY', 'ADM-25');

insert into finance.revenue_account_map (programme_code, delivery_mode_code, account_code) values
  ('AE', 'OFFLINE', 'I1.0011'),
  ('COMM', 'OFFLINE', 'I1.0012'),
  ('IELTS', 'OFFLINE', 'I1.0013'),
  ('AE', 'ONLINE', 'I1.0014'),
  ('COMM', 'ONLINE', 'I1.0015'),
  ('IELTS', 'ONLINE', 'I1.0016'),
  ('AE', 'CUSTOM', 'I1.0017'),
  ('COMM', 'CUSTOM', 'I1.0018'),
  ('IELTS', 'CUSTOM', 'I1.0019'),
  ('AE', 'CUSTOM_ONLINE', 'I1.00110'),
  ('COMM', 'CUSTOM_ONLINE', 'I1.00111'),
  ('IELTS', 'CUSTOM_ONLINE', 'I1.00112'),
  ('PE', 'OFFLINE', 'I1.00113');

-- Proficiency scales -----------------------------------------------------------------
insert into ref.proficiency_scale (scale_code, name) values ('CEFR', 'Common European Framework of Reference'), ('IELTS', 'IELTS band');
insert into ref.proficiency_level (scale_code, level_code, level_rank)
select 'CEFR', lvl, ord from unnest(array['Pre-A1','A1-','A1','A1+','A2-','A2','A2+','B1-','B1','B1+','B2','C1','C2']) with ordinality as t(lvl, ord);
insert into ref.proficiency_level (scale_code, level_code, level_rank)
select 'IELTS', to_char(b, 'FM0.0'), (b * 2)::int from generate_series(3.0, 8.5, 0.5) as b;

-- Sales funnel code tables (legacy 'Data validation' lists, translated) ---------------
insert into ref.acquisition_channel (channel_code, name, channel_group) values
  ('SOCIAL_MEDIA',        'Social media / Facebook page',      'DIGITAL'),
  ('ONLINE_ADS',          'Online ads (Facebook, Google)',     'DIGITAL'),
  ('REFERRAL_FRIEND',     'Referred by a friend or relative',  'REFERRAL'),
  ('REFERRAL_PARENT',     'Referred by another parent',        'REFERRAL'),
  ('REFERRAL_TEACHER',    'Referred by a teacher',             'REFERRAL'),
  ('RETURNING_STUDENT',   'Returning student',                 'REFERRAL'),
  ('SCHOLARSHIP_EVENT',   'Scholarship award event',           'EVENT'),
  ('EVENT',               'Event / seminar / open day',        'EVENT'),
  ('MOCK_TEST',           'Mock test day',                     'EVENT'),
  ('WALK_IN',             'Walk-in / passing by the centre',   'WALK_IN'),
  ('SCHOOL_PARTNERSHIP',  'Partner school programme',          'SCHOOL_PARTNERSHIP'),
  ('OTHER',               'Other',                             'OTHER');

insert into ref.lead_stage (stage_code, name, stage_order, is_terminal) values
  ('NEW',                   'New lead',                                1, false),
  ('CONTACTED_NO_RESPONSE', 'Contacted, no response yet',              2, false),
  ('DECLINED_APPOINTMENT',  'Declined a placement-test appointment',   3, true),
  ('TEST_BOOKED',           'Placement test booked',                   4, false),
  ('NO_SHOW',               'Booked but did not show up',              5, false),
  ('TESTED',                'Placement test completed',                6, false);

insert into ref.qualification_status (qualification_code, name) values
  ('HIGH_POTENTIAL', 'High potential'), ('LOW_POTENTIAL', 'Low potential'),
  ('NOT_A_PROSPECT', 'Not a prospect'), ('CONVERTED', 'Converted to enrolment');

insert into ref.consultation_outcome (outcome_code, name) values
  ('PENDING',                'Not processed yet'),
  ('PHONE_OFF',              'Phone switched off'),
  ('NO_ANSWER',              'No answer'),
  ('NO_SUITABLE_TIMESLOT',   'No class at a suitable time'),
  ('LOCATION_TOO_FAR',       'Location too far'),
  ('PRICE_NOT_SUITABLE',     'Price not suitable'),
  ('NO_NEED_YET',            'No need yet'),
  ('PROGRAMME_NOT_SUITABLE', 'Programme not suitable'),
  ('SUCCESS',                'Consultation successful');

insert into ref.lost_reason (reason_code, name) values
  ('PRICE', 'AMI pricing policy'), ('PROGRAMME_FIT', 'Programme does not fit'), ('SCHEDULE', 'Timetable does not fit'),
  ('NO_NEED', 'No need to study yet'), ('OTHER', 'Other reason');

insert into ref.relationship_type (relationship_code, name) values
  ('MOTHER','Mother'), ('FATHER','Father'), ('SISTER','Sister'), ('BROTHER','Brother'), ('AUNT','Aunt'),
  ('UNCLE','Uncle'), ('GRANDPARENT','Grandparent'), ('OTHER_RELATIVE','Other relative'), ('SELF','Self (adult learner)');

insert into ref.school (school_name, school_level, city, is_partner) values
  ('Riverside Primary School',          'PRIMARY',         'Bac Lieu', false),
  ('Kim Dong Primary School',           'PRIMARY',         'Bac Lieu', false),
  ('Lotus Lower Secondary School',      'LOWER_SECONDARY', 'Bac Lieu', false),
  ('City High School',                  'UPPER_SECONDARY', 'Bac Lieu', true),
  ('High School for the Gifted',        'UPPER_SECONDARY', 'Bac Lieu', true),
  ('Bac Lieu University',               'UNIVERSITY',      'Bac Lieu', false);

-- Enrolment, payment and tax code tables ---------------------------------------------
insert into ref.enrollment_status (status_code, name, is_billable, closes_receivable) values
  ('WAITLISTED', 'Waiting for a class',  true,  false),
  ('REGISTERED', 'Registered',           true,  false),
  ('ACTIVE',     'Active student',       true,  false),
  ('COMPLETED',  'Completed the course', true,  false),
  ('DROPPED',    'Dropped out mid-course', false, true),
  ('DEFERRED',   'Deferred (on hold)',   false, false),
  ('CANCELLED',  'Cancelled before start', false, true);

insert into ref.payment_method (payment_method_code, name) values ('CASH','Cash'), ('BANK_TRANSFER','Bank transfer'), ('CARD','Card');

insert into ref.vat_group (vat_code, vat_rate, description) values
  ('i0', 0.00, 'No VAT / VAT-exempt or no invoice'), ('i8', 0.08, 'Reduced VAT rate'), ('i10', 0.10, 'Standard VAT rate');

insert into ref.contract_stage (contract_stage_code, name) values ('PROBATION','Probation'), ('OFFICIAL','Official contract');

insert into ref.staff_role (role_code, name, pay_basis, is_academic, hr_code_suffix) values
  ('LA',                   'Learning Advisor (sales & student care)', 'HOURLY',  false, 'LA'),
  ('TA_AE_COMM',           'Teaching Assistant - AE / Communication', 'HOURLY',  true,  'TA'),
  ('AT_IELTS',             'Assistant Teacher - IELTS',               'HOURLY',  true,  'AT'),
  ('TEACHER_AE_COMM',      'Teacher - AE / Communication',            'HOURLY',  true,  'ACAD'),
  ('TEACHER_IELTS',        'Teacher - IELTS',                         'HOURLY',  true,  'ACAD'),
  ('FOREIGN_TEACHER',      'Foreign teacher',                         'HOURLY',  true,  'FT'),
  ('ACADEMIC_COORDINATOR', 'Academic coordinator',                    'MONTHLY', true,  'ACO'),
  ('ACADEMIC_MANAGER',     'Academic manager',                        'MONTHLY', true,  'LAM'),
  ('MARKETING',            'Marketing executive',                     'MONTHLY', false, 'MKT'),
  ('FINANCE_OFFICER',      'Finance & accounting manager',            'MONTHLY', false, 'FIN'),
  ('HR_OFFICER',           'HR & administration manager',             'MONTHLY', false, 'HRA'),
  ('CENTRE_MANAGER',       'Centre manager',                          'MONTHLY', false, 'CEN');

insert into ref.earning_type (earning_type_code, name, is_taxable, is_allowance) values
  ('LA_PAY',                'Learning Advisor pay',        true,  false),
  ('TEACHING_PAY',          'Teaching pay',                true,  false),
  ('TA_PAY',                'Teaching assistant pay',      true,  false),
  ('AT_PAY',                'Assistant teacher pay',       true,  false),
  ('FIXED_SALARY',          'Fixed monthly salary',        true,  false),
  ('COMMISSION',            'Sales commission',            true,  false),
  ('OVERTIME',              'Overtime',                    true,  false),
  ('NON_TEACHING_ACTIVITY', 'Non-teaching activities',     true,  false),
  ('OTHER_INCOME',          'Other income',                true,  false),
  ('ALLOW_LUNCH',           'Lunch allowance',             false, true),
  ('ALLOW_PHONE',           'Phone allowance',             false, true),
  ('ALLOW_BUSINESS_TRAVEL', 'Business travel allowance',   false, true),
  ('ALLOW_TRANSPORT',       'Transport allowance',         false, true);

insert into ref.deduction_type (deduction_type_code, name) values
  ('PIT','Personal income tax withheld'), ('SOCIAL_INSURANCE','Social insurance (employee share)'),
  ('HEALTH_INSURANCE','Health insurance (employee share)'), ('UNEMPLOYMENT_INSURANCE','Unemployment insurance (employee share)'),
  ('ADVANCE_RECOVERY','Recovery of salary advance');

-- Cost centres (legacy 'Cost Center' sheet) -------------------------------------------
insert into finance.cost_center (cost_center_code, name, is_academic, programme_code) values
  ('921010', 'AMI Management',        false, null),
  ('921011', 'AMI Central',           false, null),
  ('921012', 'Learning Advisor Team', false, null),
  ('921013', 'Academic Team Central', true,  null),
  ('921014', 'Marketing Team',        false, null),
  ('921015', 'Communication',         true,  'COMM'),
  ('921016', 'Applied English',       true,  'AE'),
  ('921017', 'IELTS',                 true,  'IELTS');

-- Course catalogue (legacy 'Tổng quan', 'Product Lines') -------------------------------
insert into ref.course (course_code, programme_code, name, audience, level_order, entry_level_id, exit_level_id,
                        standard_hours, default_hours_per_session, default_sessions_per_week)
select v.code, v.prog, v.name, v.aud, v.ord,
       (select level_id from ref.proficiency_level where scale_code = v.scale and level_code = v.lin),
       (select level_id from ref.proficiency_level where scale_code = v.scale and level_code = v.lout),
       v.hours, v.hps, v.spw
from (values
  ('R1','AE','Root 1','PRIMARY',1,'CEFR','Pre-A1','A1-',60,1.5,2), ('R2','AE','Root 2','PRIMARY',2,'CEFR','A1-','A1',60,1.5,2),
  ('T1','AE','Trunk 1','PRIMARY',3,'CEFR','A1','A1+',60,1.5,2),     ('T2','AE','Trunk 2','PRIMARY',4,'CEFR','A1+','A2-',60,1.5,2),
  ('L1','AE','Leaf 1','PRIMARY',5,'CEFR','A1-','A1',60,1.5,2),      ('L2','AE','Leaf 2','PRIMARY',6,'CEFR','A1','A2-',60,1.5,2),
  ('F1','AE','Flower 1','PRIMARY',7,'CEFR','A2-','A2',60,1.5,2),    ('F2','AE','Flower 2','PRIMARY',8,'CEFR','A2','A2+',60,1.5,2),
  ('S1','AE','Starter 1','SECONDARY',9,'CEFR','A1-','A1',60,1.5,3), ('B1','AE','Builder 1','SECONDARY',10,'CEFR','A1','A2-',60,1.5,3),
  ('E1','AE','Explorer 1','SECONDARY',11,'CEFR','A2','B1-',60,1.5,3), ('N1','AE','Navigator 1','SECONDARY',12,'CEFR','B1','B1+',60,1.5,3),
  ('M1','AE','Mastery 1','SECONDARY',13,'CEFR','B2','C1',60,1.5,3),
  ('A1','COMM','Communication Level 1','ADULT',1,'CEFR','A1','A2',54,1.5,3),
  ('A2','COMM','Communication Level 2','ADULT',2,'CEFR','A2','B1',54,1.5,3),
  ('A3','COMM','Communication Level 3','ADULT',3,'CEFR','B1','B2',54,1.5,3),
  ('PRE','IELTS','PRE 4.0+','HIGH_SCHOOL',1,'IELTS','3.0','4.0',72,2,3),
  ('BASIC','IELTS','BASIC 5.0+','HIGH_SCHOOL',2,'IELTS','4.0','5.0',72,2,3),
  ('PROGRESS','IELTS','PROGRESS 6.0+','HIGH_SCHOOL',3,'IELTS','5.0','6.0',72,2,4),
  ('BOOST','IELTS','BOOST 6.5+','HIGH_SCHOOL',4,'IELTS','6.0','6.5',72,2,3),
  ('PRO','IELTS','PRO 7.0+','HIGH_SCHOOL',5,'IELTS','6.5','7.0',72,2,3),
  ('G6','PE','Grade 6 support','SECONDARY',6,'CEFR','A1','A2-',48,1.5,2),
  ('G9','PE','Grade 9 support','SECONDARY',9,'CEFR','A2','B1-',48,1.5,2),
  ('G12','PE','Grade 12 exam preparation','HIGH_SCHOOL',12,'CEFR','B1-','B1+',48,1.5,2)
) as v(code, prog, name, aud, ord, scale, lin, lout, hours, hps, spw);

-- Illustrative price list; IELTS prices rise on 2025-01-01 to show effective dating ("old price" vs "new price").
insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from, effective_to)
select c.course_id, m.mode, 'FULL_COURSE',
       round(case c.programme_code when 'AE' then case c.audience when 'PRIMARY' then 4500000 else 4800000 end
                                   when 'COMM' then 4200000
                                   when 'IELTS' then 4500000 + 500000 * c.level_order
                                   when 'PE' then 2800000 end * m.factor, -3),
       '2024-06-01', case when c.programme_code = 'IELTS' then date '2025-01-01' end
from ref.course c
cross join (values ('OFFLINE', 1.0), ('ONLINE', 0.9), ('CUSTOM', 2.5)) as m(mode, factor)
where not (c.programme_code = 'PE' and m.mode <> 'OFFLINE');
insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from)
select c.course_id, m.mode, 'FULL_COURSE', round((4500000 + 500000 * c.level_order) * 1.05 * m.factor, -3), '2025-01-01'
from ref.course c cross join (values ('OFFLINE', 1.0), ('ONLINE', 0.9), ('CUSTOM', 2.5)) as m(mode, factor)
where c.programme_code = 'IELTS';
insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from)
select course_id, 'OFFLINE', 'PER_MONTH', 700000, '2024-06-01' from ref.course where programme_code = 'PE';

insert into ref.fee (fee_code, amount, effective_from) values ('MATERIALS', 200000, '2024-06-01'), ('STANDARD_DEPOSIT', 500000, '2024-06-01');

-- Payment plans (legacy 'Phương án thanh toán' + 'Gói') ---------------------------------
insert into ref.payment_plan (plan_code, name, materials_fee_applies, description) values
  ('FULL',      'Pay in full',             false, 'Whole balance due at class start'),
  ('P50_30_20', '50-30-20 instalments',    true,  '50% at start, 30% after one month, 20% after two months; materials fee added'),
  ('MONTHLY_3', 'Monthly - 3 instalments', true,  'Balance split over three monthly instalments; materials fee added'),
  ('MONTHLY_5', 'Monthly - 5 instalments', true,  'Balance split over five monthly instalments; materials fee added');
insert into ref.payment_plan_line (plan_code, seq, label, share_pct, due_offset_months) values
  ('FULL', 1, 'Full course tuition', 1.00, 0),
  ('P50_30_20', 1, '50% of tuition', 0.50, 0), ('P50_30_20', 2, '30% of tuition', 0.30, 1), ('P50_30_20', 3, '20% of tuition', 0.20, 2),
  ('MONTHLY_3', 1, 'Month 1', 0.34, 0), ('MONTHLY_3', 2, 'Month 2', 0.33, 1), ('MONTHLY_3', 3, 'Month 3', 0.33, 2),
  ('MONTHLY_5', 1, 'Month 1', 0.20, 0), ('MONTHLY_5', 2, 'Month 2', 0.20, 1), ('MONTHLY_5', 3, 'Month 3', 0.20, 2),
  ('MONTHLY_5', 4, 'Month 4', 0.20, 3), ('MONTHLY_5', 5, 'Month 5', 0.20, 4);

-- Discounts (legacy 'Chương trình giảm giá', 'Đăng ký theo nhóm') ----------------------------
insert into ref.discount_programme (discount_code, name, discount_kind, discount_value, valid_from, valid_to, requires_approval, is_scholarship) values
  ('OPENING_20',        'Grand-opening promotion 20%',      'PERCENT', 0.20, '2024-06-01', '2024-09-30', false, false),
  ('SALES_TACTIC_5',    'Sales tactic 5%',                  'PERCENT', 0.05, '2024-06-01', null,         false, false),
  ('RETURNING_5',       'Returning student 5%',             'PERCENT', 0.05, '2024-06-01', null,         false, false),
  ('EARLY_BIRD_10',     'Early-bird 10%',                   'PERCENT', 0.10, '2025-01-01', null,         false, false),
  ('PARTNER_SCHOOL_30', 'Partner-school scholarship 30%',   'PERCENT', 0.30, '2024-06-01', null,         true,  true),
  ('SCHOLARSHIP_70',    'Opening scholarship 70%',          'PERCENT', 0.70, '2024-06-01', '2024-09-30', true,  true),
  ('SCHOLARSHIP_100',   'Full scholarship 100%',            'PERCENT', 1.00, '2024-06-01', null,         true,  true);
insert into ref.group_discount_tier (tier_code, min_group_size, discount_amount) values
  ('GROUP_2', 2, 200000), ('GROUP_4', 4, 300000), ('GROUP_6', 6, 400000);

-- Salary codes and illustrative hourly rates (legacy 'Salary Pipeline') -----------------
insert into ref.salary_code (salary_code, role_code, contract_stage_code) values
  ('S/L.001','LA','PROBATION'),              ('S/L.002','LA','OFFICIAL'),
  ('S/L.003','AT_IELTS','PROBATION'),        ('S/L.005','AT_IELTS','OFFICIAL'),
  ('S/L.004','TA_AE_COMM','PROBATION'),      ('S/L.006','TA_AE_COMM','OFFICIAL'),
  ('S/L.007','TEACHER_AE_COMM','PROBATION'), ('S/L.009','TEACHER_AE_COMM','OFFICIAL'),
  ('S/L.008','TEACHER_IELTS','PROBATION'),   ('S/L.010','TEACHER_IELTS','OFFICIAL'),
  ('S/L.011','FOREIGN_TEACHER','OFFICIAL');
insert into ref.salary_rate (salary_code, hourly_rate, effective_from) values
  ('S/L.001', 22000, '2024-06-01'), ('S/L.002', 25000, '2024-06-01'),
  ('S/L.003', 30000, '2024-06-01'), ('S/L.005', 40000, '2024-06-01'),
  ('S/L.004', 27000, '2024-06-01'), ('S/L.006', 30000, '2024-06-01'),
  ('S/L.007', 80000, '2024-06-01'), ('S/L.009', 100000, '2024-06-01'),
  ('S/L.008', 150000, '2024-06-01'), ('S/L.010', 200000, '2024-06-01'),
  ('S/L.011', 400000, '2024-06-01');

-- Payroll -> GL mapping (most specific match wins) -----------------------------------
insert into finance.earning_account_map (earning_type_code, role_code, programme_code, delivery_mode_code, account_code)
select 'TEACHING_PAY', null, p, m, a from (values
  ('AE','OFFLINE','E1.0011'), ('COMM','OFFLINE','E1.0012'), ('IELTS','OFFLINE','E1.0013'),
  ('AE','ONLINE','E1.0014'),  ('COMM','ONLINE','E1.0015'),  ('IELTS','ONLINE','E1.0016'),
  ('AE','CUSTOM','E1.0017'),  ('COMM','CUSTOM','E1.0018'),  ('IELTS','CUSTOM','E1.0019'),
  ('AE','CUSTOM_ONLINE','E1.00110'), ('COMM','CUSTOM_ONLINE','E1.00111'), ('IELTS','CUSTOM_ONLINE','E1.00112'),
  ('PE','OFFLINE','E1.0011')) as t(p, m, a)
union all
select 'TEACHING_PAY', 'FOREIGN_TEACHER', p, m, a from (values
  ('AE','OFFLINE','E1.0061'), ('COMM','OFFLINE','E1.0062'), ('IELTS','OFFLINE','E1.0063'),
  ('AE','ONLINE','E1.0064'),  ('COMM','ONLINE','E1.0065'),  ('IELTS','ONLINE','E1.0066')) as t(p, m, a)
union all
select e, null, p, m, a from (values ('TA_PAY'), ('AT_PAY')) as et(e) cross join (values
  ('AE','OFFLINE','E1.0021'), ('COMM','OFFLINE','E1.0022'), ('IELTS','OFFLINE','E1.0023'),
  ('AE','ONLINE','E1.0024'),  ('COMM','ONLINE','E1.0025'),  ('IELTS','ONLINE','E1.0026'),
  ('AE','CUSTOM','E1.0027'),  ('COMM','CUSTOM','E1.0028'),  ('IELTS','CUSTOM','E1.0029'),
  ('PE','OFFLINE','E1.0021')) as t(p, m, a)
union all
select * from (values
  ('LA_PAY',                null::text,             null::text, null::text, 'E1.003'),
  ('FIXED_SALARY',          'MARKETING',            null, null, 'E1.005'),
  ('FIXED_SALARY',          'CENTRE_MANAGER',       null, null, 'E1.020'),
  ('FIXED_SALARY',          'ACADEMIC_COORDINATOR', null, null, 'E1.004'),
  ('FIXED_SALARY',          'ACADEMIC_MANAGER',     null, null, 'E1.021'),
  ('COMMISSION',            null, null, null, 'E1.014'),
  ('OVERTIME',              null, null, null, 'E1.011'),
  ('OVERTIME',              'LA', null, null, 'E1.014'),
  ('NON_TEACHING_ACTIVITY', null, null, null, 'E1.016'),
  ('OTHER_INCOME',          null, null, null, 'E1.014'),
  ('ALLOW_PHONE',           null, null, null, 'E8.017'),
  ('ALLOW_LUNCH',           null, null, null, 'E1.013'),
  ('ALLOW_TRANSPORT',       null, null, null, 'E1.013'),
  ('ALLOW_BUSINESS_TRAVEL', null, null, null, 'E1.013'),
  ('FIXED_SALARY',          'FINANCE_OFFICER',      null, null, 'E1.005'),
  ('FIXED_SALARY',          'HR_OFFICER',           null, null, 'E1.005')) as t;

-- Payroll tax rules ---------------------------------------------------------------------
insert into payroll.pit_rule (employment_type, threshold_amount, rate, effective_from, note) values
  ('PART_TIME',  2000000, 0.10, '2024-01-01', 'Legacy rule: 10% withheld when taxable income in the month exceeds 2,000,000 VND'),
  ('CONTRACTOR', 2000000, 0.10, '2024-01-01', 'Same flat withholding as part-time staff'),
  ('FULL_TIME',  2000000, 0.10, '2024-01-01', 'Legacy workbook applied the same flat rule to all staff; progressive PIT is out of scope');
insert into payroll.statutory_deduction_rule (deduction_type_code, employment_type, employee_rate, effective_from) values
  ('SOCIAL_INSURANCE', 'FULL_TIME', 0.080, '2024-01-01'),
  ('HEALTH_INSURANCE', 'FULL_TIME', 0.015, '2024-01-01'),
  ('UNEMPLOYMENT_INSURANCE', 'FULL_TIME', 0.010, '2024-01-01');

-- Rooms ------------------------------------------------------------------------------------
insert into academic.closure_day (closure_date, reason)
select d::date, v.reason
from (values ('2025-01-01', '2025-01-01', 'New Year''s Day'),
             ('2025-01-27', '2025-02-02', 'Lunar New Year (Tet)'),
             ('2025-04-07', '2025-04-07', 'Hung Kings Commemoration Day'),
             ('2025-04-30', '2025-05-01', 'Reunification Day and Labour Day'),
             ('2025-09-01', '2025-09-02', 'National Day'),
             ('2026-01-01', '2026-01-01', 'New Year''s Day'),
             ('2026-02-14', '2026-02-22', 'Lunar New Year (Tet)'),
             ('2026-04-27', '2026-04-27', 'Hung Kings Commemoration Day (observed)'),
             ('2026-04-30', '2026-05-01', 'Reunification Day and Labour Day'),
             ('2026-09-01', '2026-09-02', 'National Day'),
             ('2027-01-01', '2027-01-01', 'New Year''s Day'),
             ('2027-02-04', '2027-02-12', 'Lunar New Year (Tet)'),
             ('2027-04-16', '2027-04-16', 'Hung Kings Commemoration Day'),
             ('2027-04-30', '2027-05-01', 'Reunification Day and Labour Day'),
             ('2027-09-02', '2027-09-03', 'National Day')) as v(d_from, d_to, reason)
cross join lateral generate_series(v.d_from::date, v.d_to::date, interval '1 day') d;

insert into academic.room (room_name, capacity, is_online, is_hybrid) values
  ('Room 101', 15, false, false), ('Room 102', 15, false, true), ('Room 201', 20, false, false), ('Online room', 30, true, false);

-- Control catalogue (control matrix) -------------------------------------------------------
insert into ctl.control (control_code, name, domain, risk, rule, check_view, frequency, severity, owner_role_code, app_role_code, business_rule) values
  ('SAL-01','Lead without owner or channel','SALES','Leads are not followed up and marketing ROI cannot be measured','Every open lead has a Learning Advisor and an acquisition channel','ctl.v_chk_sal_01_lead_incomplete','DAILY','MEDIUM','LA','LEARNING_ADVISOR','BR-11'),
  ('SAL-02','Enrolment without placement test','SALES','Learners placed in the wrong level; output commitment cannot be kept','Every enrolment created from a lead has a completed placement test','ctl.v_chk_sal_02_enrolled_without_test','WEEKLY','MEDIUM','LA','LEARNING_ADVISOR','BR-11'),
  ('BIL-01','Enrolment without payment schedule','BILLING','Tuition is never billed or followed up','Every billable enrolment has a payment schedule','ctl.v_chk_bil_01_no_schedule','DAILY','HIGH','CENTRE_MANAGER','FINANCE_MANAGER','BR-04'),
  ('BIL-02','Schedule does not match price','BILLING','Learners are billed more or less than the agreed price','Sum of schedule lines = net payable after discounts','ctl.v_chk_bil_02_schedule_mismatch','DAILY','HIGH','CENTRE_MANAGER','FINANCE_MANAGER','BR-04'),
  ('BIL-03','Overdue instalments','BILLING','Cash shortfall and growing bad debt','Instalments unpaid more than 30 days after due date','ctl.v_chk_bil_03_overdue','WEEKLY','HIGH','LA','LEARNING_ADVISOR','BR-06'),
  ('BIL-04','Unapplied cash','BILLING','Receipts not linked to tuition: revenue and receivables misstated','Every issued receipt is fully allocated to instalments','ctl.v_chk_bil_04_unapplied_cash','DAILY','MEDIUM','CENTRE_MANAGER','FINANCE_MANAGER','BR-05'),
  ('BIL-05','Discount waiting for approval','BILLING','Revenue leakage through unapproved discounts','Scholarships and discounts above 30% are approved by the Finance Manager','ctl.v_chk_bil_05_discount_policy','DAILY','HIGH','CENTRE_MANAGER','FINANCE_MANAGER','BR-04'),
  ('BIL-06','Uncollectible balance not written off','BILLING','Receivables overstated for dropped-out learners','Earned tuition of closed enrolments is collected or written off','ctl.v_chk_bil_06_uncollectible','MONTHLY','MEDIUM','CENTRE_MANAGER','FINANCE_MANAGER','BR-06'),
  ('BIL-07','Paid but no class after 30 days','BILLING','Learner dissatisfaction and refund risk; revenue cannot be earned','Paid enrolments are placed in a class within 30 days','ctl.v_chk_bil_07_paid_without_class','WEEKLY','MEDIUM','ACADEMIC_COORDINATOR','ACADEMIC_MANAGER','BR-11'),
  ('BIL-08','Payment does not match instalment','BILLING','Receipts recorded with wrong amounts or partial payments not followed up','Instalments partially paid for more than 7 days','ctl.v_chk_bil_08_partial_payment','WEEKLY','LOW','LA','LEARNING_ADVISOR','BR-06'),
  ('BIL-09','Cash not closed or difference unexplained','BILLING','Cash collected at the desk goes missing','Every day with cash receipts is closed by the collector; differences are reviewed','ctl.v_chk_bil_09_cash_close','DAILY','HIGH','CENTRE_MANAGER','FINANCE_MANAGER','BR-05'),
  ('ACA-01','Class over capacity','ACADEMIC','Teaching quality and room safety','Active learners <= class capacity','ctl.v_chk_aca_01_over_capacity','WEEKLY','LOW','ACADEMIC_COORDINATOR','ACADEMIC_MANAGER','BR-03'),
  ('ACA-02','Session not confirmed','ACADEMIC','Teachers not paid correctly; payroll disputes','Every past session is confirmed as delivered (with hours) or cancelled within 3 days','ctl.v_chk_aca_02_unconfirmed_hours','WEEKLY','MEDIUM','ACADEMIC_COORDINATOR','ACADEMIC_MANAGER','BR-07'),
  ('ACA-03','Class without a teacher','ACADEMIC','Classes sold to learners with nobody to teach them','Open and running classes have a lead teacher','ctl.v_chk_aca_03_no_teacher','DAILY','HIGH','ACADEMIC_COORDINATOR','ACADEMIC_MANAGER','BR-11'),
  ('PAY-01','Hours without a pay rate','PAYROLL','Staff paid zero or at a wrong rate','Every confirmed hour has a valid hourly rate on its date','ctl.v_chk_pay_01_missing_rate','PERIOD_CLOSE','HIGH','CENTRE_MANAGER','HR_MANAGER','BR-07'),
  ('PAY-02','Commission on unpaid / cancelled enrolment','PAYROLL','Commission paid on revenue never collected','Commission only for fully paid, active enrolments','ctl.v_chk_pay_02_commission_at_risk','PERIOD_CLOSE','MEDIUM','CENTRE_MANAGER','HR_MANAGER','BR-07'),
  ('PAY-03','Payslip does not match payroll lines','PAYROLL','Wrong net pay','Payslip taxable earnings = sum of taxable payroll lines','ctl.v_chk_pay_03_payslip_mismatch','PERIOD_CLOSE','HIGH','CENTRE_MANAGER','HR_MANAGER','BR-07'),
  ('EXP-01','Payment without invoice','EXPENSES','Non-deductible costs and weak audit trail','Payments >= threshold carry a VAT invoice','ctl.v_chk_exp_01_no_invoice','MONTHLY','LOW','CENTRE_MANAGER','FINANCE_MANAGER','BR-11'),
  ('EXP-02','Capex not capitalised','EXPENSES','Assets missing from the register; P&L distorted','Every capex voucher line has a fixed asset','ctl.v_chk_exp_02_capex_without_asset','MONTHLY','MEDIUM','CENTRE_MANAGER','FINANCE_MANAGER','BR-11'),
  ('EXP-03','Unclassified or mis-coded spend','EXPENSES','Costs reported on the wrong P&L line','Voucher lines use postable expense accounts and active cost centres','ctl.v_chk_exp_03_miscoded','DAILY','MEDIUM','CENTRE_MANAGER','FINANCE_MANAGER','BR-11'),
  ('REP-01','Revenue not fully recognised','REPORTING','Accrual P&L and deferred revenue misstated','A finished enrolment has earned exactly its contract value','ctl.v_chk_rep_01_revenue_completeness','PERIOD_CLOSE','HIGH','CENTRE_MANAGER','FINANCE_MANAGER','BR-10');

-- Sales commission rule (configurable; the demo value is illustrative) ---------------------
insert into payroll.commission_rule (role_code, basis, rate, earn_event, effective_from, note) values
  ('LA', 'PCT_OF_NET_TUITION', 0.03, 'FULLY_PAID', '2024-01-01', 'Illustrative: 3% of net tuition, earned in the month the enrolment is fully paid');
