"""Seed script to populate the database with real player data."""
from datetime import date, datetime, timedelta
from app import app, db
from models import Player, Session, Attendance, Payment

def seed_database():
    with app.app_context():
        # Clear existing data
        Attendance.query.delete()
        Payment.query.delete()
        Session.query.delete()
        Player.query.delete()
        db.session.commit()

        # Real player data from spreadsheet
        players_data = [
            {'name': 'Adalarasu Parthiban', 'email': 'p.adalarasu@gmail.com', 'phone': '952-486-9204'},
            {'name': 'Adithya', 'email': 'adityakarthikkumarv@gmail.com', 'phone': '614-588-3882'},
            {'name': 'Arun Sundaram', 'email': 'arunsun@gmail.com', 'phone': '703-861-0489'},
            {'name': 'Ashwin Deshmukh', 'email': 'ashwindeshmukhd@gmail.com', 'phone': '440-313-1715'},
            {'name': 'Aswin Jayaraj', 'email': 'aswinedwin21@gmail.com', 'phone': '571-525-8583'},
            {'name': 'Bakiaraj Venkatachalam', 'email': 'bakiaraj@gmail.com', 'phone': '571-528-6657'},
            {'name': 'Balaji Natarajan', 'email': 'bala.shop25@gmail.com', 'phone': '408-425-8476'},
            {'name': 'Barath Rajarathnam', 'email': 'barath.rajaratnam@gmail.com', 'phone': '703-981-4810'},
            {'name': 'Baskar Radhakrishnan', 'email': 'rbas0722@gmail.com', 'phone': '571-443-1353'},
            {'name': 'Bhanu Emmadi', 'email': 'bhanuemmadi@gmail.com', 'phone': '571-230-8877'},
            {'name': 'Bharath Rajashekaran', 'email': 'btrajasekaran@gmail.com', 'phone': '972-757-8655'},
            {'name': 'Bharath Srinivasan', 'email': 'bharathgsvp@gmail.com', 'phone': '978-319-0683'},
            {'name': 'Deepak Budhiraja', 'email': 'budhiraja.deepak@gmail.com', 'phone': '434-409-5672'},
            {'name': 'Ganesh Rajagopal', 'email': 'gans.rajagopal@gmail.com', 'phone': '908-463-5454'},
            {'name': 'Ganesh Manivannan', 'email': 'mganesh.tn@gmail.com', 'phone': '732-763-7674'},
            {'name': 'Karthik Padhmanabhan', 'email': 'karthik.padmanabhan78@gmail.com', 'phone': '804-938-3356'},
            {'name': 'Loga', 'email': 'loganathanr@gmail.com', 'phone': '571-474-4178'},
            {'name': 'Mazhar', 'email': 'mazharullaha@gmail.com', 'phone': '901-283-1977'},
            {'name': 'Muthu Arigovindan', 'email': 'vasari856@gmail.com', 'phone': None},
            {'name': 'Muthu Sekar', 'email': 'muthu.sekar1@gmail.com', 'phone': '716-479-4327'},
            {'name': 'Nagarajan', 'email': 'mknagarajan@gmail.com', 'phone': '703-269-8898'},
            {'name': 'Naresh Balasubramani', 'email': 'nareshbk@gmail.com', 'phone': '202-527-4930'},
            {'name': 'Nevil Shakespeare', 'email': 'nevilshakespeare@gmail.com', 'phone': '703-623-0157'},
            {'name': 'Padmanabhan Ponniah Raju', 'email': 'padmanabanraju@gmail.com', 'phone': '562-673-8517'},
            {'name': 'Param Madhavan', 'email': 'm.param@gmail.com', 'phone': '202-650-7004'},
            {'name': 'Prasanna', 'email': 'prasannababu5@gmail.com', 'phone': None},
            {'name': 'Rajesh', 'email': 'samdolls@gmail.com', 'phone': '703-909-4825'},
            {'name': 'Ramesh Nagamani', 'email': 'ramesh13@gmail.com', 'phone': '540-454-0491'},
            {'name': 'Saran', 'email': 'mailnsaran@gmail.com', 'phone': '919-802-3574'},
            {'name': 'Saravanan Kalai', 'email': 'saravanan.kalaivanan@gmail.com', 'phone': '415-691-5204'},
            {'name': 'Saravanan SR', 'email': 'saravanansr@gmail.com', 'phone': '248-924-7282'},
            {'name': 'Satish Sivakolundhu', 'email': 'satish069@gmail.com', 'phone': '704-264-7069'},
            {'name': 'Senthil', 'email': 'senthil.kp.22@gmail.com', 'phone': '201-428-7075'},
            {'name': 'Siraj', 'email': 'siraj.nr@gmail.com', 'phone': '571-499-9981'},
            {'name': 'Siva', 'email': 'Sivainnet@gmail.com', 'phone': '202-820-5040'},
            {'name': 'Srinivas Pothula', 'email': 'reddy.244@gmail.com', 'phone': '571-544-0225'},
            {'name': 'Srinivas Sundaragopal', 'email': 'srini.sundar@gmail.com', 'phone': '716-228-2411'},
            {'name': 'Sudheer', 'email': 'sudheer1078@gmail.com', 'phone': '469-354-1700'},
            {'name': 'Thiyagu KL', 'email': 'klthiyagu@gmail.com', 'phone': '571-208-7764'},
            {'name': 'Thoufiq', 'email': 'mailjillu98@gmail.com', 'phone': '202-352-1179'},
            {'name': 'Udai Bhanu', 'email': 'dychauhan@gmail.com', 'phone': '407-745-7508'},
            {'name': 'Venkatesh Varalu', 'email': 'varalu@gmail.com', 'phone': '224-829-9443'},
            {'name': 'Vijay Alan Sargunam', 'email': 'vijay.alan@gmail.com', 'phone': '408-472-7563'},
            {'name': 'Vinoth Kalimuthu', 'email': 'vinothkalimuthu@gmail.com', 'phone': '919-904-8052'},
        ]

        players = []
        for data in players_data:
            player = Player(
                name=data['name'],
                category='regular',
                email=data['email'],
                phone=data['phone']
            )
            db.session.add(player)
            players.append(player)
        db.session.commit()

        print(f"Database seeded successfully!")
        print(f"Created {len(players)} players")


if __name__ == '__main__':
    seed_database()
