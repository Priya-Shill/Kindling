"""
Official BLS SOC 2018 major and minor group titles — a public,
published classification standard (https://www.bls.gov/soc/), not an
invented taxonomy. Only entries that actually appear among our 923
occupations (Outputs/career_graph.json) are included, verified against
the real O*NET-SOC codes present in that file.

If a minor-group code is ever encountered that isn't in
MINOR_GROUP_TITLES (e.g. the occupation dataset is refreshed later),
minor_title() falls back to the major group's own title rather than
guessing at a name — never a fabricated minor-group label.
"""

MAJOR_GROUP_TITLES = {
    "11": "Management Occupations",
    "13": "Business and Financial Operations Occupations",
    "15": "Computer and Mathematical Occupations",
    "17": "Architecture and Engineering Occupations",
    "19": "Life, Physical, and Social Science Occupations",
    "21": "Community and Social Service Occupations",
    "23": "Legal Occupations",
    "25": "Educational Instruction and Library Occupations",
    "27": "Arts, Design, Entertainment, Sports, and Media Occupations",
    "29": "Healthcare Practitioners and Technical Occupations",
    "31": "Healthcare Support Occupations",
    "33": "Protective Service Occupations",
    "35": "Food Preparation and Serving Related Occupations",
    "37": "Building and Grounds Cleaning and Maintenance Occupations",
    "39": "Personal Care and Service Occupations",
    "41": "Sales and Related Occupations",
    "43": "Office and Administrative Support Occupations",
    "45": "Farming, Fishing, and Forestry Occupations",
    "47": "Construction and Extraction Occupations",
    "49": "Installation, Maintenance, and Repair Occupations",
    "51": "Production Occupations",
    "53": "Transportation and Material Moving Occupations",
}

MINOR_GROUP_TITLES = {
    "11-1": "Top Executives",
    "11-2": "Advertising, Marketing, Promotions, Public Relations, and Sales Managers",
    "11-3": "Operations Specialties Managers",
    "11-9": "Other Management Occupations",
    "13-1": "Business Operations Specialists",
    "13-2": "Financial Specialists",
    "15-1": "Computer Occupations",
    "15-2": "Mathematical Science Occupations",
    "17-1": "Architects, Surveyors, and Cartographers",
    "17-2": "Engineers",
    "17-3": "Drafters, Engineering Technicians, and Mapping Technicians",
    "19-1": "Life Scientists",
    "19-2": "Physical Scientists",
    "19-3": "Social Scientists and Related Workers",
    "19-4": "Life, Physical, and Social Science Technicians",
    "19-5": "Occupational Health and Safety Specialists and Technicians",
    "21-1": "Counselors, Social Workers, and Other Community and Social Service Specialists",
    "21-2": "Religious Workers",
    "23-1": "Lawyers, Judges, and Related Workers",
    "23-2": "Legal Support Workers",
    "25-1": "Postsecondary Teachers",
    "25-2": "Preschool, Elementary, Middle, Secondary, and Special Education Teachers",
    "25-3": "Other Teachers and Instructors",
    "25-4": "Librarians, Curators, and Archivists",
    "25-9": "Other Educational Instruction and Library Workers",
    "27-1": "Art and Design Workers",
    "27-2": "Entertainers and Performers, Sports and Related Workers",
    "27-3": "Media and Communication Workers",
    "27-4": "Media and Communication Equipment Workers",
    "29-1": "Healthcare Diagnosing or Treating Practitioners",
    "29-2": "Health Technologists and Technicians",
    "29-9": "Other Healthcare Practitioners and Technical Occupations",
    "31-1": "Home Health, Personal Care, and Nursing Assistants",
    "31-2": "Occupational and Physical Therapist Assistants and Aides",
    "31-9": "Other Healthcare Support Occupations",
    "33-1": "Supervisors of Protective Service Workers",
    "33-2": "Firefighting and Prevention Workers",
    "33-3": "Law Enforcement Workers",
    "33-9": "Other Protective Service Workers",
    "35-1": "Supervisors of Food Preparation and Serving Workers",
    "35-2": "Cooks and Food Preparation Workers",
    "35-3": "Food and Beverage Serving Workers",
    "35-9": "Other Food Preparation and Serving Related Workers",
    "37-1": "Supervisors of Building and Grounds Cleaning and Maintenance Workers",
    "37-2": "Building Cleaning and Pest Control Workers",
    "37-3": "Grounds Maintenance Workers",
    "39-1": "Supervisors of Personal Care and Service Workers",
    "39-2": "Animal Care and Service Workers",
    "39-3": "Entertainment Attendants and Related Workers",
    "39-4": "Funeral Service Workers",
    "39-5": "Personal Appearance Workers",
    "39-6": "Baggage Porters, Bellhops, and Concierges",
    "39-7": "Tour and Travel Guides",
    "39-9": "Other Personal Care and Service Workers",
    "41-1": "Supervisors of Sales Workers",
    "41-2": "Retail Sales Workers",
    "41-3": "Sales Representatives, Services",
    "41-4": "Sales Representatives, Wholesale and Manufacturing",
    "41-9": "Other Sales and Related Workers",
    "43-1": "Supervisors of Office and Administrative Support Workers",
    "43-2": "Communications Equipment Operators",
    "43-3": "Financial Clerks",
    "43-4": "Information and Record Clerks",
    "43-5": "Material Recording, Scheduling, Dispatching, and Distributing Workers",
    "43-6": "Secretaries and Administrative Assistants",
    "43-9": "Other Office and Administrative Support Workers",
    "45-1": "Supervisors of Farming, Fishing, and Forestry Workers",
    "45-2": "Agricultural Workers",
    "45-3": "Fishing and Hunting Workers",
    "45-4": "Forest, Conservation, and Logging Workers",
    "47-1": "Supervisors of Construction and Extraction Workers",
    "47-2": "Construction Trades Workers",
    "47-3": "Helpers, Construction Trades",
    "47-4": "Other Construction and Related Workers",
    "47-5": "Extraction Workers",
    "49-1": "Supervisors of Installation, Maintenance, and Repair Workers",
    "49-2": "Electrical and Electronic Equipment Mechanics, Installers, and Repairers",
    "49-3": "Vehicle and Mobile Equipment Mechanics, Installers, and Repairers",
    "49-9": "Other Installation, Maintenance, and Repair Occupations",
    "51-1": "Supervisors of Production Workers",
    "51-2": "Assemblers and Fabricators",
    "51-3": "Food Processing Workers",
    "51-4": "Metal Workers and Plastic Workers",
    "51-5": "Printing Workers",
    "51-6": "Textile, Apparel, and Furnishings Workers",
    "51-7": "Woodworkers",
    "51-8": "Plant and System Operators",
    "51-9": "Other Production Occupations",
    "53-1": "Supervisors of Transportation and Material Moving Workers",
    "53-2": "Air Transportation Workers",
    "53-3": "Motor Vehicle Operators",
    "53-4": "Rail Transportation Workers",
    "53-5": "Water Transportation Workers",
    "53-6": "Other Transportation Workers",
    "53-7": "Material Moving Workers",
}


FIELD_DISPLAY_MAJOR_LABELS = {
    "11": "Management & Leadership",
    "13": "Business & Finance",
    "15": "Computing & Mathematics",
    "17": "Engineering & Architecture",
    "19": "Science & Research",
    "21": "Community & Social Services",
    "23": "Law",
    "25": "Education & Teaching",
    "27": "Arts, Media & Entertainment",
    "29": "Healthcare",
    "31": "Healthcare Support",
    "33": "Protective & Safety Services",
    "35": "Food & Hospitality",
    "37": "Building & Grounds Maintenance",
    "39": "Personal Care & Services",
    "41": "Sales",
    "43": "Office & Administrative Support",
    "45": "Farming, Fishing & Forestry",
    "47": "Construction & Trades",
    "49": "Installation & Repair",
    "51": "Manufacturing & Production",
    "53": "Transportation & Logistics",
}

FIELD_DISPLAY_MINOR_LABELS = {
    "11-1": "Executive Leadership",
    "11-2": "Marketing & PR Management",
    "11-3": "Operations Management",
    "11-9": "Other Management Roles",
    "13-1": "Business Operations",
    "13-2": "Finance",
    "15-1": "Computing & Software",
    "15-2": "Mathematics & Statistics",
    "17-1": "Architecture & Surveying",
    "17-2": "Engineering",
    "17-3": "Engineering Technology",
    "19-1": "Life Sciences",
    "19-2": "Physical Sciences",
    "19-3": "Social Sciences",
    "19-4": "Science Technicians",
    "19-5": "Health & Safety Specialists",
    "21-1": "Counseling & Social Work",
    "21-2": "Religious & Spiritual Work",
    "23-1": "Law & Judiciary",
    "23-2": "Legal Support",
    "25-1": "College & University Teaching",
    "25-2": "School Teaching",
    "25-3": "Other Teaching & Instruction",
    "25-4": "Libraries & Archives",
    "25-9": "Other Education Roles",
    "27-1": "Art & Design",
    "27-2": "Performing Arts",
    "27-3": "Media & Communication",
    "27-4": "Media & Sound Technology",
    "29-1": "Medicine & Therapy",
    "29-2": "Health Technology & Technicians",
    "29-9": "Other Healthcare Roles",
    "31-1": "Nursing & Personal Care Assistance",
    "31-2": "Therapy Assistance",
    "31-9": "Other Healthcare Support",
    "33-1": "Protective Services Supervision",
    "33-2": "Firefighting",
    "33-3": "Law Enforcement",
    "33-9": "Other Protective Services",
    "35-1": "Food Service Supervision",
    "35-2": "Cooking & Food Prep",
    "35-3": "Food & Beverage Service",
    "35-9": "Other Food Service Roles",
    "37-1": "Facilities Supervision",
    "37-2": "Cleaning & Pest Control",
    "37-3": "Grounds & Landscaping",
    "39-1": "Personal Services Supervision",
    "39-2": "Animal Care",
    "39-3": "Entertainment & Recreation Support",
    "39-4": "Funeral Services",
    "39-5": "Hair, Beauty & Personal Appearance",
    "39-6": "Hospitality Support",
    "39-7": "Tours & Travel Guiding",
    "39-9": "Other Personal Services",
    "41-1": "Sales Supervision",
    "41-2": "Retail Sales",
    "41-3": "Service Sales",
    "41-4": "Wholesale & Manufacturing Sales",
    "41-9": "Other Sales Roles",
    "43-1": "Office Supervision",
    "43-2": "Communications Equipment Operation",
    "43-3": "Financial Clerical Work",
    "43-4": "Records & Information Clerking",
    "43-5": "Scheduling & Dispatching",
    "43-6": "Administrative Assistance",
    "43-9": "Other Office Support",
    "45-1": "Farming Supervision",
    "45-2": "Agriculture",
    "45-3": "Fishing & Hunting",
    "45-4": "Forestry & Conservation",
    "47-1": "Construction Supervision",
    "47-2": "Construction Trades",
    "47-3": "Construction Trade Helpers",
    "47-4": "Other Construction Roles",
    "47-5": "Mining & Extraction",
    "49-1": "Repair & Maintenance Supervision",
    "49-2": "Electronics Repair",
    "49-3": "Vehicle Repair",
    "49-9": "Other Repair & Maintenance",
    "51-1": "Production Supervision",
    "51-2": "Assembly & Fabrication",
    "51-3": "Food Processing",
    "51-4": "Metal & Plastics Work",
    "51-5": "Printing",
    "51-6": "Textiles & Apparel",
    "51-7": "Woodworking",
    "51-8": "Plant & Systems Operation",
    "51-9": "Other Production Roles",
    "53-1": "Transportation Supervision",
    "53-2": "Air Transportation",
    "53-3": "Driving & Motor Vehicle Operation",
    "53-4": "Rail Transportation",
    "53-5": "Water Transportation",
    "53-6": "Other Transportation Roles",
    "53-7": "Material Handling & Moving",
}


# Broad groups (first 6 chars) - a field only gets this granular when
# its minor group is split (see career_tree.group_into_fields), or
# when every occupation shown in it belongs to the one broad group.
# Only groups whose real members in Outputs/career_graph.json were
# checked are listed; the rest fall back to their minor group's label.
FIELD_DISPLAY_BROAD_LABELS = {
    "11-202": "Marketing & Sales Management",
    "11-303": "Financial Management",
    "11-903": "Education Administration",
    "13-108": "Logistics & Project Management",
    "13-116": "Market Research",
    "13-205": "Financial Analysis & Advice",
    "15-121": "Systems & Security Analysis",
    "15-123": "IT Support",
    "15-124": "Networks & Databases",
    "15-125": "Software & Web Development",
    "15-204": "Statistics",
    "15-205": "Data Science",
    "17-101": "Architecture",
    "17-102": "Surveying & Mapping",
    "17-205": "Civil Engineering",
    "17-207": "Electrical & Electronics Engineering",
    "17-211": "Industrial & Safety Engineering",
    "17-214": "Mechanical Engineering",
    "17-219": "Specialist Engineering",
    "17-301": "Drafting",
    "17-302": "Engineering Technology",
    "19-101": "Agricultural & Food Science",
    "19-102": "Biology",
    "19-103": "Conservation & Forestry",
    "19-104": "Medical Science",
    "19-201": "Physics & Astronomy",
    "19-203": "Chemistry & Materials Science",
    "19-204": "Environmental & Earth Science",
    "19-301": "Economics",
    "19-303": "Psychology",
    "19-401": "Agricultural & Food Technicians",
    "19-404": "Environmental & Geological Technicians",
    "21-101": "Counseling",
    "21-102": "Social Work",
    "21-109": "Community Health & Support",
    "23-101": "Law Practice",
    "23-102": "Judges & Mediators",
    "25-102": "Maths & Computing Teaching (College)",
    "25-103": "Engineering & Architecture Teaching (College)",
    "25-104": "Life Sciences Teaching (College)",
    "25-105": "Physical Sciences Teaching (College)",
    "25-106": "Social Sciences Teaching (College)",
    "25-107": "Health Teaching (College)",
    "25-108": "Education Teaching (College)",
    "25-111": "Law & Social Work Teaching (College)",
    "25-112": "Arts & Humanities Teaching (College)",
    "25-201": "Preschool & Kindergarten Teaching",
    "25-202": "Elementary & Middle School Teaching",
    "25-203": "Secondary School Teaching",
    "25-205": "Special Education",
    "25-401": "Museums & Archives",
    "25-904": "Teaching Assistance",
    "27-101": "Art & Animation",
    "27-102": "Design",
    "27-201": "Acting, Producing & Directing",
    "27-202": "Sports & Coaching",
    "27-203": "Dance",
    "27-204": "Music",
    "27-304": "Writing & Editing",
    "27-309": "Translation & Captioning",
    "27-401": "Sound, Light & Broadcast Technology",
    "27-403": "Film & Video",
    "29-102": "Dentistry",
    "29-112": "Therapy",
    "29-114": "Nursing",
    "29-121": "Medicine",
    "29-122": "Specialist Medicine",
    "29-124": "Surgery",
    "29-201": "Medical Laboratory Work",
    "29-203": "Medical Imaging",
    "29-204": "Emergency Medical Care",
}

# The one minor group whose everyday name hides half its members:
# 27-2000 is officially "Entertainers and Performers, Sports and
# Related Workers", so "Performing Arts" alone would mislabel a field
# that also shows athletes, coaches or referees (broad group 27-202).
SPORTS_BROAD_GROUP = "27-202"
PERFORMING_ARTS_AND_SPORTS_LABEL = "Performing Arts & Sports"


def field_display_label(field_code: str, member_ids=()) -> str:
    """
    Neutral, student-friendly name for a field node - hand-written
    (not AI-generated, not derived from occupation titles at request
    time) so it's stable and never phrased oddly by a model, unlike
    the official BLS title it's shown alongside (field_title()/
    minor_title()/major_title() - kept real and unchanged, the panel
    shows both). Falls back to the real official title if a code ever
    shows up that isn't in this hand-written set (e.g. the dataset is
    refreshed later) - never a fabricated label.

    member_ids are the SOC ids actually shown in the field. When they
    all sit in one broad group that has its own label, that more
    specific label is used ("Dance" for a Performing Arts field that
    only holds Dancers and Choreographers).
    """
    if len(field_code) == 2:
        return FIELD_DISPLAY_MAJOR_LABELS.get(field_code, major_title(field_code))

    member_broads = {field_code} if len(field_code) == 6 else {soc_id[:6] for soc_id in member_ids}
    if len(member_broads) == 1:
        only = next(iter(member_broads))
        if only in FIELD_DISPLAY_BROAD_LABELS:
            return FIELD_DISPLAY_BROAD_LABELS[only]

    key = field_code[:4]
    if key == SPORTS_BROAD_GROUP[:4] and SPORTS_BROAD_GROUP in member_broads:
        return PERFORMING_ARTS_AND_SPORTS_LABEL
    if key in FIELD_DISPLAY_MINOR_LABELS:
        return FIELD_DISPLAY_MINOR_LABELS[key]
    return minor_title(key)


def major_group(soc_id: str) -> str:
    """'15-2041.00' -> '15'"""
    return soc_id[:2]


def minor_group(soc_id: str) -> str:
    """'15-2041.00' -> '15-2'"""
    return soc_id[:4]


def broad_group(soc_id: str) -> str:
    """'15-2041.00' -> '15-204'"""
    return soc_id[:6]


def major_title(code: str) -> str:
    return MAJOR_GROUP_TITLES.get(code, "General Occupations")


def minor_title(code: str) -> str:
    if code in MINOR_GROUP_TITLES:
        return MINOR_GROUP_TITLES[code]
    return major_title(code[:2])
