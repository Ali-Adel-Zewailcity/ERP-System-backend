import sys
import os
from datetime import datetime, date, time, timedelta
from decimal import Decimal
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import sqlalchemy as sa
from app.core.config import settings
from app.db.metadata import metadata
from app.schema import *

def seed_database():
    print("Starting database seeding...")
    engine = sa.create_engine(settings.SYNC_DATABASE_URL)
    
    with engine.begin() as conn:
        print("Connected to database. Deleting old transactional data...")
        
        # Delete in correct order to avoid FK violations
        tables_to_clear = [
            "return_items", "returns", "sales_order_items", "sales_orders",
            "purchase_order_items", "purchase_orders", "supplier_products", "suppliers",
            "inventory_stock", "products", "product_categories", "payroll",
            "leave_requests", "attendance", "employee_attachments", "employees",
            "departments", "activity_logs"
        ]
        
        for table in tables_to_clear:
            try:
                conn.execute(sa.text(f'DELETE FROM "{table}"'))
                print(f"Cleared table: {table}")
            except Exception as e:
                print(f"Error clearing {table}: {e}")
                
        org_id = 1
        print(f"Seeding data for Organization ID: {org_id}")
        
        # 1. Seed Departments
        depts_data = [
            {"org_id": org_id, "name": "Human Resources", "manager_id": 3},
            {"org_id": org_id, "name": "Inventory & Logistics", "manager_id": 4},
            {"org_id": org_id, "name": "Sales & Marketing", "manager_id": 2},
            {"org_id": org_id, "name": "Finance & Accounting", "manager_id": 2},
            {"org_id": org_id, "name": "IT & Technical Support", "manager_id": 2}
        ]
        
        dept_ids = []
        for dept in depts_data:
            res = conn.execute(
                departments.insert().values(
                    org_id=dept["org_id"],
                    name=dept["name"],
                    manager_id=dept["manager_id"]
                ).returning(departments.c.id, departments.c.name)
            ).fetchone()
            dept_ids.append((res[0], res[1]))
            print(f"Created Department: {res[1]} (ID: {res[0]})")
            
        # 2. Seed Employees
        employees_data = [
            {"full_name": "Ahmed Mamdouh", "emp_num": "EMP-2026-001", "email": "ahmed.mamdouh@company.com", "phone": "+201001234567", "title": "Senior HR Specialist", "dept": "Human Resources", "salary": 14500.00, "hire_date": date(2024, 3, 15)},
            {"full_name": "Sara Abdelrahman", "emp_num": "EMP-2026-002", "email": "sara.abdelrahman@company.com", "phone": "+201112223334", "title": "HR Coordinator", "dept": "Human Resources", "salary": 8500.00, "hire_date": date(2025, 1, 10)},
            {"full_name": "Mahmoud Hassan", "emp_num": "EMP-2026-003", "email": "mahmoud.hassan@company.com", "phone": "+201223334445", "title": "Warehouse Supervisor", "dept": "Inventory & Logistics", "salary": 11000.00, "hire_date": date(2023, 6, 1)},
            {"full_name": "Karim Taha", "emp_num": "EMP-2026-004", "email": "karim.taha@company.com", "phone": "+201554443322", "title": "Logistics Coordinator", "dept": "Inventory & Logistics", "salary": 9500.00, "hire_date": date(2024, 8, 20)},
            {"full_name": "Mayada Elshafey", "emp_num": "EMP-2026-005", "email": "mayada.elshafey@company.com", "phone": "+201098765432", "title": "Senior Sales Representative", "dept": "Sales & Marketing", "salary": 12000.00, "hire_date": date(2023, 11, 1)},
            {"full_name": "Youssef Gindy", "emp_num": "EMP-2026-006", "email": "youssef.gindy@company.com", "phone": "+201145678901", "title": "Sales Account Manager", "dept": "Sales & Marketing", "salary": 16000.00, "hire_date": date(2022, 5, 15)},
            {"full_name": "Amr Diab", "emp_num": "EMP-2026-007", "email": "amr.diab@company.com", "phone": "+201276543210", "title": "Chief Accountant", "dept": "Finance & Accounting", "salary": 22000.00, "hire_date": date(2021, 1, 1)},
            {"full_name": "Noha Sherif", "emp_num": "EMP-2026-008", "email": "noha.sherif@company.com", "phone": "+201023456789", "title": "Junior Accountant", "dept": "Finance & Accounting", "salary": 7500.00, "hire_date": date(2025, 2, 15)},
            {"full_name": "Ziad Ammar", "emp_num": "EMP-2026-009", "email": "ziad.ammar@company.com", "phone": "+201134567890", "title": "IT Support Engineer", "dept": "IT & Technical Support", "salary": 10500.00, "hire_date": date(2024, 1, 15)},
            {"full_name": "Rania Shawky", "emp_num": "EMP-2026-010", "email": "rania.shawky@company.com", "phone": "+201245678901", "title": "System Administrator", "dept": "IT & Technical Support", "salary": 18000.00, "hire_date": date(2022, 9, 10)}
        ]
        
        emp_ids = []
        for emp in employees_data:
            res = conn.execute(
                employees.insert().values(
                    org_id=org_id,
                    full_name=emp["full_name"],
                    employee_number=emp["emp_num"],
                    email=emp["email"],
                    phone_number=emp["phone"],
                    job_title=emp["title"],
                    department=emp["dept"],
                    salary=Decimal(str(emp["salary"])),
                    hire_date=emp["hire_date"],
                    status="active"
                ).returning(employees.c.id, employees.c.full_name)
            ).fetchone()
            emp_ids.append((res[0], res[1], emp["salary"]))
            print(f"Created Employee: {res[1]} (ID: {res[0]})")
        # 3. Seed Attendance (Last 30 days)
        print("Generating attendance records...")
        start_date = date(2026, 1, 1)
        end_date = date(2026, 1, 30)
        current_day = start_date
        
        attendance_records = []
        while current_day <= end_date:
            # Skip weekends (Friday = 4, Saturday = 5 in python weekday where Monday = 0)
            if current_day.weekday() in (4, 5):
                current_day += timedelta(days=1)
                continue
                
            for emp_id, name, _ in emp_ids:
                rand = random.random()
                if rand < 0.85:
                    status = "present"
                    check_in = time(8, random.randint(30, 59), random.randint(0, 59))
                    check_out = time(17, random.randint(0, 30), random.randint(0, 59))
                elif rand < 0.95:
                    status = "late"
                    check_in = time(9, random.randint(15, 45), random.randint(0, 59))
                    check_out = time(17, random.randint(0, 15), random.randint(0, 59))
                elif rand < 0.98:
                    status = "leave"
                    check_in = None
                    check_out = None
                else:
                    status = "absent"
                    check_in = None
                    check_out = None
                    
                attendance_records.append({
                    "org_id": org_id,
                    "employee_id": emp_id,
                    "attendance_date": current_day,
                    "check_in_time": check_in,
                    "check_out_time": check_out,
                    "status": status,
                    "source": "biometric" if status in ("present", "late") else "web",
                    "notes": "Regular check-in" if status == "present" else ("Late arrival" if status == "late" else None)
                })
            current_day += timedelta(days=1)
            
        # Bulk insert attendance
        conn.execute(attendance.insert(), attendance_records)
        print(f"Inserted {len(attendance_records)} attendance records.")
        
        # 4. Seed Leave Requests
        print("Generating leave requests...")
        leave_types = ["annual", "sick", "unpaid", "emergency"]
        leave_statuses = ["approved", "pending", "rejected"]
        
        for emp_id, name, _ in emp_ids[:5]: # Generate for first 5 employees
            for _ in range(random.randint(1, 2)):
                l_type = random.choice(leave_types)
                l_status = random.choice(leave_statuses)
                start_l = date(2026, random.randint(2, 3), random.randint(1, 10))
                days_count = random.randint(1, 5)
                end_l = start_l + timedelta(days=days_count - 1)
                
                conn.execute(
                    leave_requests.insert().values(
                        employee_id=emp_id,
                        leave_type=l_type,
                        start_date=start_l,
                        end_date=end_l,
                        total_days=days_count,
                        status=l_status,
                        reason=f"Requesting {l_type} leave for personal reasons.",
                        approved_by=3 if l_status == "approved" else None,
                        resolved_at=datetime.now() if l_status in ("approved", "rejected") else None
                    )
                )
        print("Leave requests seeded.")
        # 5. Seed Payroll (Last 3 months)
        print("Generating payroll records...")
        months_years = [(11, 2025), (12, 2025), (1, 2026)]
        
        for month, year in months_years:
            for emp_id, name, base_salary in emp_ids:
                # Calculate realistic payroll values
                base = Decimal(str(base_salary))
                allowances = base * Decimal("0.10") # 10% allowance
                overtime = Decimal(str(random.randint(500, 1500)))
                deductions = base * Decimal("0.15") # 15% taxes/social security
                
                # Randomly add some extra deductions for absences
                if random.random() < 0.2:
                    deductions += Decimal(str(random.randint(200, 600)))
                    
                gross = base + allowances + overtime
                net = gross - deductions
                
                conn.execute(
                    payroll.insert().values(
                        org_id=org_id,
                        employee_id=emp_id,
                        month=month,
                        year=year,
                        days_worked=22,
                        absences=random.randint(0, 2),
                        overtime_hours=Decimal(str(random.randint(0, 10))),
                        bonus=Decimal(str(random.randint(500, 1500))),
                        allowance=allowances,
                        deductions=deductions,
                        gross_salary=gross,
                        net_salary=net,
                        status="paid" if (year < 2026 or (year == 2026 and month < 1)) else "pending",
                        notes=f"Monthly payslip for {month}/{year}"
                    )
                )
        print("Payroll records seeded.")
        # 6. Seed Product Categories
        print("Generating product categories...")
        categories_data = [
            {"name": "Electronics & Gadgets", "description": "Laptops, phones, and office electronics"},
            {"name": "Office Furniture", "description": "Ergonomic chairs, desks, and storage cabinets"},
            {"name": "Industrial Raw Materials", "description": "Steel sheets, aluminum profiles, and fasteners"},
            {"name": "Packaging Materials", "description": "Heavy duty cardboard boxes, bubble wrap, and tape"},
            {"name": "Safety Equipment", "description": "Helmets, safety vests, gloves, and protective eyewear"}
        ]
        
        cat_ids = []
        for cat in categories_data:
            res = conn.execute(
                product_categories.insert().values(
                    org_id=org_id,
                    name=cat["name"],
                    description=cat["description"]
                ).returning(product_categories.c.id, product_categories.c.name)
            ).fetchone()
            cat_ids.append((res[0], res[1]))
            print(f"Created Category: {res[1]} (ID: {res[0]})")
            
        # 7. Seed Products
        print("Generating products...")
        products_data = [
            {"sku": "ELEC-LD-001", "name": "Dell Latitude 5420 Laptop", "desc": "Intel i5, 16GB RAM, 512GB SSD", "price": 24500.00, "cost": 18000.00, "cat": "Electronics & Gadgets"},
            {"sku": "ELEC-MS-002", "name": "Logitech MX Master 3S Mouse", "desc": "Ergonomic wireless mouse with silent clicks", "price": 3200.00, "cost": 2100.00, "cat": "Electronics & Gadgets"},
            {"sku": "FURN-CH-001", "name": "Ergonomic Mesh Office Chair", "desc": "High-back chair with lumbar support and 3D armrests", "price": 6500.00, "cost": 4200.00, "cat": "Office Furniture"},
            {"sku": "FURN-DK-002", "name": "Adjustable Standing Desk", "desc": "Dual-motor electric height adjustable desk (140x70cm)", "price": 12500.00, "cost": 8500.00, "cat": "Office Furniture"},
            {"sku": "RAW-ST-001", "name": "Stainless Steel Sheet 304", "desc": "2B finish, 1.5mm thickness, 1220x2440mm", "price": 4500.00, "cost": 3100.00, "cat": "Industrial Raw Materials"},
            {"sku": "RAW-AL-002", "name": "Aluminum Profile 4040", "desc": "T-slot extruded aluminum profile, 3 meters length", "price": 850.00, "cost": 550.00, "cat": "Industrial Raw Materials"},
            {"sku": "PACK-BX-001", "name": "Heavy Duty Cardboard Box", "desc": "Double-wall corrugated box (40x40x40cm), pack of 50", "price": 1200.00, "cost": 800.00, "cat": "Packaging Materials"},
            {"sku": "PACK-TP-002", "name": "Industrial Packaging Tape", "desc": "Brown acrylic adhesive tape, 48mm x 100m, pack of 6", "price": 350.00, "cost": 220.00, "cat": "Packaging Materials"},
            {"sku": "SAFE-HM-001", "name": "Industrial Safety Helmet", "desc": "ABS shell safety helmet with 6-point suspension", "price": 450.00, "cost": 280.00, "cat": "Safety Equipment"},
            {"sku": "SAFE-GL-002", "name": "Cut-Resistant Work Gloves", "desc": "Nitrile coated HPPE gloves, Level 5 protection, pack of 10", "price": 950.00, "cost": 600.00, "cat": "Safety Equipment"}
        ]
        
        prod_ids = []
        for prod in products_data:
            # Find category ID
            cat_id = next(cid for cid, cname in cat_ids if cname == prod["cat"])
            res = conn.execute(
                products.insert().values(
                    org_id=org_id,
                    category_id=cat_id,
                    sku=prod["sku"],
                    name=prod["name"],
                    description=prod["desc"],
                    unit_price=Decimal(str(prod["price"])),
                    cost_price=Decimal(str(prod["cost"])),
                    is_active=True
                ).returning(products.c.id, products.c.name, products.c.unit_price, products.c.cost_price)
            ).fetchone()
            prod_ids.append((res[0], res[1], res[2], res[3]))
            print(f"Created Product: {res[1]} (ID: {res[0]})")
            
        # 8. Seed Inventory Stock (1-to-1 with products)
        print("Generating inventory stock levels...")
        for pid, name, _, _ in prod_ids:
            # Random stock levels
            qty_avail = random.randint(10, 150)
            qty_res = random.randint(0, 15)
            reorder_th = random.randint(15, 30)
            
            # Make some products low stock to trigger alerts
            if random.random() < 0.2:
                qty_avail = random.randint(2, 10)
                reorder_th = 15
                
            conn.execute(
                inventory_stock.insert().values(
                    product_id=pid,
                    quantity_available=qty_avail,
                    quantity_reserved=qty_res,
                    reorder_threshold=reorder_th
                )
            )
        print("Inventory stock seeded.")
        # 9. Seed Suppliers
        print("Generating suppliers...")
        suppliers_data = [
            {"name": "El-Araby Group", "contact": "Mahmoud El-Araby", "email": "info@elarabygroup.com", "phone": "+201009988776", "address": "Benha, Qalyubia, Egypt"},
            {"name": "Global Steel Suppliers Ltd", "contact": "John Smith", "email": "sales@globalsteel.com", "phone": "+442079460192", "address": "London, UK"},
            {"name": "Modern Office Solutions", "contact": "Tarek Mansour", "email": "tarek@modernoffice.com", "phone": "+201115554443", "address": "Nasr City, Cairo, Egypt"},
            {"name": "Safety First Co.", "contact": "Amr Abdelhady", "email": "amr@safetyfirst.com", "phone": "+201224445556", "address": "6th of October City, Giza, Egypt"},
            {"name": "Apex Packaging Solutions", "contact": "Sherif Hegazi", "email": "sherif@apexpack.com", "phone": "+201553332221", "address": "Obour City, Egypt"}
        ]
        
        supp_ids = []
        for supp in suppliers_data:
            res = conn.execute(
                suppliers.insert().values(
                    org_id=org_id,
                    name=supp["name"],
                    contact_name=supp["contact"],
                    email=supp["email"],
                    phone=supp["phone"],
                    address=supp["address"],
                    is_active=True
                ).returning(suppliers.c.id, suppliers.c.name)
            ).fetchone()
            supp_ids.append((res[0], res[1]))
            print(f"Created Supplier: {res[1]} (ID: {res[0]})")
            
        # 10. Seed Supplier Products (M2M)
        print("Generating supplier-product mappings...")
        for pid, name, _, cost in prod_ids:
            # Map products to suppliers based on category
            if "ELEC" in name or "Dell" in name or "Logitech" in name:
                supp_id = next(sid for sid, sname in supp_ids if sname == "El-Araby Group")
            elif "FURN" in name or "Chair" in name or "Desk" in name:
                supp_id = next(sid for sid, sname in supp_ids if sname == "Modern Office Solutions")
            elif "RAW" in name or "Steel" in name or "Aluminum" in name:
                supp_id = next(sid for sid, sname in supp_ids if sname == "Global Steel Suppliers Ltd")
            elif "PACK" in name or "Box" in name or "Tape" in name:
                supp_id = next(sid for sid, sname in supp_ids if sname == "Apex Packaging Solutions")
            else:
                supp_id = next(sid for sid, sname in supp_ids if sname == "Safety First Co.")
                
            conn.execute(
                supplier_products.insert().values(
                    supplier_id=supp_id,
                    product_id=pid,
                    supplier_sku=f"SUPP-{name[:4].upper()}-{random.randint(100, 999)}",
                    supplier_price=cost * Decimal("0.95"), # Supplier price is slightly lower than cost
                    lead_time_days=random.randint(3, 10),
                    is_preferred=True
                )
            )
        print("Supplier-product mappings seeded.")
        
        # 11. Seed Purchase Orders
        print("Generating purchase orders...")
        po_statuses = ["draft", "ordered", "partially_received", "received", "cancelled"]
        
        for i in range(6):
            supp_id, sname = random.choice(supp_ids)
            status = po_statuses[i % len(po_statuses)]
            
            res = conn.execute(
                purchase_orders.insert().values(
                    org_id=org_id,
                    supplier_id=supp_id,
                    created_by=4, # mem1 (inventory manager)
                    status=status,
                    total_amount=Decimal("0.00"),
                    notes=f"Purchase order for restocking from {sname}.",
                    ordered_at=datetime.now() - timedelta(days=random.randint(5, 15)) if status != "draft" else None,
                    received_at=datetime.now() - timedelta(days=random.randint(1, 4)) if status == "received" else None
                ).returning(purchase_orders.c.id)
            ).fetchone()
            po_id = res[0]
            
            # Add items to PO
            po_total = Decimal("0.00")
            selected_prods = random.sample(prod_ids, random.randint(1, 3))
            for pid, pname, _, cost in selected_prods:
                qty_ord = random.randint(10, 50)
                qty_rec = qty_ord if status == "received" else (random.randint(1, qty_ord - 1) if status == "partially_received" else 0)
                unit_cost = cost * Decimal("0.95")
                
                conn.execute(
                    purchase_order_items.insert().values(
                        order_id=po_id,
                        product_id=pid,
                        quantity_ordered=qty_ord,
                        quantity_received=qty_rec,
                        unit_cost=unit_cost
                    )
                )
                po_total += unit_cost * qty_ord
                
            # Update PO total
            conn.execute(
                purchase_orders.update().where(purchase_orders.c.id == po_id).values(total_amount=po_total)
            )
        print("Purchase orders seeded.")
        # 12. Seed Customers
        print("Generating customers...")
        customers_data = [
            {"name": "Nile Holding Group", "email": "procurement@nileholding.com", "phone": "+201002223334", "address": "Zamalek, Cairo, Egypt", "credit": 250000.00},
            {"name": "Cairo Construction Company", "email": "info@cairoconst.com", "phone": "+201113334445", "address": "New Cairo, Egypt", "credit": 500000.00},
            {"name": "Alexandria Trading Corp", "email": "sales@alextrading.com", "phone": "+201224445556", "address": "Smouha, Alexandria, Egypt", "credit": 150000.00},
            {"name": "Saudi Logistics Solutions", "email": "contact@saudilogistics.com", "phone": "+966114567890", "address": "Riyadh, KSA", "credit": 300000.00},
            {"name": "Ahmad Al-Otaibi (Retail)", "email": "ahmad@otaibi.com", "phone": "+966501234567", "address": "Jeddah, KSA", "credit": 50000.00},
            {"name": "Delta Manufacturing", "email": "factory@deltamanf.com", "phone": "+201556667778", "address": "Tanta, Gharbia, Egypt", "credit": 400000.00},
            {"name": "TechVantage Solutions", "email": "it@techvantage.com", "phone": "+201099887766", "address": "Maadi, Cairo, Egypt", "credit": 200000.00},
            {"name": "Global Trade Corp", "email": "import@globaltrade.com", "phone": "+201144332211", "address": "Port Said, Egypt", "credit": 350000.00}
        ]
        
        cust_ids = []
        for cust in customers_data:
            res = conn.execute(
                customers.insert().values(
                    org_id=org_id,
                    name=cust["name"],
                    email=cust["email"],
                    phone=cust["phone"],
                    address=cust["address"],
                    credit_limit=Decimal(str(cust["credit"])),
                    is_active=True
                ).returning(customers.c.id, customers.c.name)
            ).fetchone()
            cust_ids.append((res[0], res[1]))
            print(f"Created Customer: {res[1]} (ID: {res[0]})")
            
        # 13. Seed Sales Orders
        print("Generating sales orders...")
        so_statuses = ["draft", "confirmed", "processing", "shipped", "delivered", "cancelled"]
        
        so_ids = []
        for i in range(12):
            cust_id, cname = random.choice(cust_ids)
            status = so_statuses[i % len(so_statuses)]
            
            res = conn.execute(
                sales_orders.insert().values(
                    org_id=org_id,
                    customer_id=cust_id,
                    created_by=2, # aa1 (owner/sales manager)
                    status=status,
                    total_amount=Decimal("0.00"),
                    notes=f"Sales order for {cname}.",
                    confirmed_at=datetime.now() - timedelta(days=random.randint(5, 10)) if status != "draft" else None,
                    shipped_at=datetime.now() - timedelta(days=random.randint(2, 4)) if status in ("shipped", "delivered") else None,
                    delivered_at=datetime.now() - timedelta(days=random.randint(1, 2)) if status == "delivered" else None,
                    cancelled_at=datetime.now() - timedelta(days=random.randint(1, 2)) if status == "cancelled" else None
                ).returning(sales_orders.c.id, sales_orders.c.status)
            ).fetchone()
            so_ids.append((res[0], res[1]))
            
            # Add items to SO
            so_total = Decimal("0.00")
            selected_prods = random.sample(prod_ids, random.randint(1, 3))
            for pid, pname, price, _ in selected_prods:
                qty = random.randint(1, 10)
                unit_price = price
                
                conn.execute(
                    sales_order_items.insert().values(
                        order_id=res[0],
                        product_id=pid,
                        quantity=qty,
                        unit_price=unit_price
                    )
                )
                so_total += unit_price * qty
                
            # Update SO total
            conn.execute(
                sales_orders.update().where(sales_orders.c.id == res[0]).values(total_amount=so_total)
            )
        print("Sales orders seeded.")
        # 14. Seed Returns
        print("Generating returns...")
        return_statuses = ["pending", "approved", "rejected", "completed"]
        
        # Select delivered sales orders to return
        delivered_sos = [sid for sid, status in so_ids if status == "delivered"]
        if not delivered_sos:
            delivered_sos = [so_ids[0][0]]
            
        for i, so_id in enumerate(delivered_sos[:3]):
            status = return_statuses[i % len(return_statuses)]
            
            res = conn.execute(
                returns.insert().values(
                    org_id=org_id,
                    order_id=so_id,
                    processed_by=2, # aa1
                    reason=random.choice(["Defective item", "Wrong specification", "Damaged during shipping"]),
                    status=status,
                    refund_amount=Decimal("0.00"),
                    resolved_at=datetime.now() if status in ("approved", "rejected", "completed") else None
                ).returning(returns.c.id)
            ).fetchone()
            ret_id = res[0]
            
            # Add items to return
            # Fetch items from the sales order
            so_items = conn.execute(
                sa.select(sales_order_items.c.product_id, sales_order_items.c.quantity, sales_order_items.c.unit_price)
                .where(sales_order_items.c.order_id == so_id)
            ).fetchall()
            
            refund_total = Decimal("0.00")
            for item in so_items:
                ret_qty = random.randint(1, item[1]) if item[1] > 1 else 1
                conn.execute(
                    return_items.insert().values(
                        return_id=ret_id,
                        product_id=item[0],
                        quantity=ret_qty,
                        inspection_status="pass" if status == "completed" else None,
                        refund_method="bank_transfer" if status == "completed" else None
                    )
                )
                refund_total += item[2] * ret_qty
                
            # Update return refund amount
            conn.execute(
                returns.update().where(returns.c.id == ret_id).values(refund_amount=refund_total)
            )
        print("Returns seeded.")
        
        # 15. Seed Activity Logs
        print("Generating activity logs...")
        modules = ["inventory", "sales", "hr", "auth", "reporting", "system"]
        actions = ["create", "update", "delete", "approve", "reject", "login"]
        
        for _ in range(25):
            mod = random.choice(modules)
            act = random.choice(actions)
            user_id = random.choice([2, 3, 4])
            
            conn.execute(
                activity_logs.insert().values(
                    org_id=org_id,
                    user_id=user_id,
                    module=mod,
                    action=f"{act}_{mod}_entity",
                    entity_type=mod.capitalize(),
                    entity_id=random.randint(1, 10),
                    old_value=None,
                    new_value=f"User performed {act} on {mod} module.",
                    ip_address=f"192.168.1.{random.randint(10, 254)}",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            )
        print("Activity logs seeded.")
        print("\nDatabase seeding completed successfully! Your ERP is now fully populated with professional, realistic data.")

if __name__ == "__main__":
    seed_database()
