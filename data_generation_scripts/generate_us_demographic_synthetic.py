import os, re, json, math, time, gzip, random, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from faker import Faker

SEED = int(os.environ.get('SEED', '20260818'))
ID_OFFSET = int(os.environ.get('ID_OFFSET', '0'))
N_ROWS = int(os.environ.get('N_ROWS', '5000000'))
CHUNK = int(os.environ.get('CHUNK', '200000'))
OUTDIR = Path(os.environ.get('OUTDIR', '/mnt/data'))
OUT = OUTDIR / os.environ.get('OUT_NAME', f'usa_demographic_synthetic_{N_ROWS}_rows.csv.gz')
SUMMARY = OUTDIR / os.environ.get('SUMMARY_NAME', 'usa_demographic_synthetic_summary.json')
STATE_REF = OUTDIR / 'usa_demographic_state_reference.csv'
SAMPLE = OUTDIR / os.environ.get('SAMPLE_NAME', 'usa_demographic_synthetic_sample_10000.csv')

rng = np.random.default_rng(SEED)
random.seed(SEED)

# Exact state ranking/weight anchor from U.S. Census Bureau 2020 urban/rural state workbook.
URBAN = {
'CA':('California',37259490,94.2366),'TX':('Texas',24400697,83.7203),'FL':('Florida',19714806,91.5342),
'NY':('New York',17665166,87.4459),'IL':('Illinois',11137590,86.9275),'PA':('Pennsylvania',9941070,76.4539),
'OH':('Ohio',9001099,76.2841),'NJ':('New Jersey',8708779,93.7537),'GA':('Georgia',7933986,74.0670),
'MI':('Michigan',7404258,73.4744),'NC':('North Carolina',6964727,66.7159),'VA':('Virginia',6528313,75.6345),
'WA':('Washington',6424035,83.3718),'MA':('Massachusetts',6416895,91.2798),'AZ':('Arizona',6385230,89.2852),
'MD':('Maryland',5288760,85.6171),'CO':('Colorado',4966936,86.0267),'IN':('Indiana',4829686,71.1763),
'TN':('Tennessee',4577282,66.2334),'MO':('Missouri',4275663,69.4675),'MN':('Minnesota',4101754,71.8787),
'WI':('Wisconsin',3953691,67.0831),'SC':('South Carolina',3477869,67.9480),'OR':('Oregon',3410984,80.4998),
'LA':('Louisiana',3332237,71.5417),'CT':('Connecticut',3110153,86.2507),'UT':('Utah',2937303,89.7814)
}
STATE_CODES=list(URBAN)
STATE_NAMES=np.array([URBAN[s][0] for s in STATE_CODES],dtype=object)
urban_counts=np.array([URBAN[s][1] for s in STATE_CODES],dtype=float)
STATE_P=urban_counts/urban_counts.sum()

# Approximate 2020-2024 ACS/QuickFacts-style state parameters used as calibration targets.
# These are synthetic calibration values, not row-level Census records.
CFG = {
'CA':(100300,.222,.156,.502,.37,.27,[.34,.40,.055,.16,.005,.004,.036]),
'TX':(78000,.248,.136,.503,.32,.17,[.39,.40,.12,.055,.006,.001,.028]),
'FL':(74000,.194,.218,.510,.34,.21,[.50,.27,.17,.03,.003,.001,.026]),
'NY':(85000,.206,.187,.514,.40,.23,[.52,.20,.15,.09,.003,.001,.036]),
'IL':(83000,.218,.173,.509,.38,.14,[.58,.18,.14,.06,.002,.001,.037]),
'PA':(77000,.205,.200,.510,.35,.08,[.70,.09,.11,.04,.002,.001,.057]),
'OH':(71000,.217,.189,.509,.31,.05,[.72,.045,.13,.03,.002,.001,.072]),
'NJ':(103000,.218,.177,.511,.44,.23,[.51,.22,.13,.10,.002,.001,.037]),
'GA':(78000,.232,.153,.512,.34,.11,[.50,.11,.31,.045,.003,.001,.031]),
'MI':(72000,.214,.195,.507,.32,.07,[.72,.06,.14,.034,.005,.001,.040]),
'NC':(76000,.223,.175,.512,.36,.09,[.61,.11,.22,.035,.010,.001,.034]),
'VA':(90000,.215,.169,.506,.42,.13,[.60,.11,.19,.07,.004,.001,.025]),
'WA':(96000,.214,.171,.500,.40,.15,[.64,.14,.045,.10,.013,.007,.055]),
'MA':(104000,.196,.181,.512,.48,.17,[.68,.13,.075,.075,.002,.001,.037]),
'AZ':(77000,.225,.188,.504,.33,.13,[.53,.32,.055,.04,.030,.002,.023]),
'MD':(101000,.224,.164,.513,.43,.16,[.49,.12,.30,.07,.003,.001,.016]),
'CO':(93000,.211,.155,.498,.45,.10,[.65,.23,.04,.04,.010,.001,.029]),
'IN':(71000,.230,.175,.507,.29,.06,[.76,.08,.10,.025,.002,.001,.032]),
'TN':(72000,.221,.177,.512,.31,.06,[.72,.07,.17,.02,.003,.001,.016]),
'MO':(73000,.221,.182,.509,.32,.05,[.74,.05,.15,.022,.004,.001,.033]),
'MN':(85000,.230,.174,.502,.40,.09,[.72,.06,.08,.055,.010,.001,.074]),
'WI':(76000,.216,.190,.504,.32,.06,[.77,.075,.065,.030,.006,.001,.053]),
'SC':(72000,.215,.192,.515,.32,.06,[.63,.06,.25,.020,.004,.001,.035]),
'OR':(83000,.202,.196,.506,.38,.10,[.71,.14,.025,.050,.014,.004,.057]),
'LA':(60000,.233,.165,.512,.27,.04,[.55,.07,.32,.020,.007,.001,.032]),
'CT':(93000,.203,.196,.512,.43,.15,[.66,.17,.10,.050,.002,.001,.017]),
'UT':(96000,.282,.117,.497,.38,.09,[.77,.15,.015,.025,.010,.006,.024]),
}

CITIES={
'CA':[('Los Angeles','900',['213','310']),('San Diego','921',['619','858']),('San Jose','951',['408','669']),('San Francisco','941',['415','628']),('Sacramento','958',['916','279']),('Fresno','937',['559'])],
'TX':[('Houston','770',['713','281']),('Dallas','752',['214','469']),('Austin','787',['512','737']),('San Antonio','782',['210']),('Fort Worth','761',['817','682']),('El Paso','799',['915'])],
'FL':[('Miami','331',['305','786']),('Orlando','328',['407','689']),('Tampa','336',['813']),('Jacksonville','322',['904']),('Fort Lauderdale','333',['954','754'])],
'NY':[('New York','100',['212','646']),('Brooklyn','112',['718','347']),('Buffalo','142',['716']),('Rochester','146',['585']),('Albany','122',['518']),('Syracuse','132',['315'])],
'IL':[('Chicago','606',['312','773']),('Aurora','605',['630']),('Rockford','611',['815']),('Springfield','627',['217'])],
'PA':[('Philadelphia','191',['215','267']),('Pittsburgh','152',['412','878']),('Allentown','181',['610']),('Harrisburg','171',['717']),('Erie','165',['814'])],
'OH':[('Columbus','432',['614']),('Cleveland','441',['216']),('Cincinnati','452',['513']),('Toledo','436',['419']),('Akron','443',['330'])],
'NJ':[('Newark','071',['973']),('Jersey City','073',['201']),('Paterson','075',['973']),('Trenton','086',['609']),('Edison','088',['732'])],
'GA':[('Atlanta','303',['404','470']),('Savannah','314',['912']),('Augusta','309',['706']),('Columbus','319',['706'])],
'MI':[('Detroit','482',['313']),('Grand Rapids','495',['616']),('Ann Arbor','481',['734']),('Lansing','489',['517']),('Flint','485',['810'])],
'NC':[('Charlotte','282',['704','980']),('Raleigh','276',['919','984']),('Greensboro','274',['336']),('Durham','277',['919']),('Winston-Salem','271',['336'])],
'VA':[('Virginia Beach','234',['757']),('Richmond','232',['804']),('Norfolk','235',['757']),('Alexandria','223',['703','571']),('Arlington','222',['703','571'])],
'WA':[('Seattle','981',['206']),('Spokane','992',['509']),('Tacoma','984',['253']),('Bellevue','980',['425']),('Vancouver','986',['360'])],
'MA':[('Boston','021',['617','857']),('Worcester','016',['508']),('Springfield','011',['413']),('Cambridge','021',['617']),('Lowell','018',['978'])],
'AZ':[('Phoenix','850',['602']),('Tucson','857',['520']),('Mesa','852',['480']),('Scottsdale','852',['480']),('Chandler','852',['480'])],
'MD':[('Baltimore','212',['410','443']),('Silver Spring','209',['301','240']),('Rockville','208',['301','240']),('Frederick','217',['301']),('Columbia','210',['410'])],
'CO':[('Denver','802',['303','720']),('Colorado Springs','809',['719']),('Aurora','800',['303','720']),('Fort Collins','805',['970']),('Boulder','803',['303'])],
'IN':[('Indianapolis','462',['317']),('Fort Wayne','468',['260']),('Evansville','477',['812']),('South Bend','466',['574']),('Carmel','460',['317'])],
'TN':[('Nashville','372',['615']),('Memphis','381',['901']),('Knoxville','379',['865']),('Chattanooga','374',['423'])],
'MO':[('St. Louis','631',['314']),('Kansas City','641',['816']),('Springfield','658',['417']),('Columbia','652',['573'])],
'MN':[('Minneapolis','554',['612']),('St. Paul','551',['651']),('Rochester','559',['507']),('Duluth','558',['218'])],
'WI':[('Milwaukee','532',['414']),('Madison','537',['608']),('Green Bay','543',['920']),('Kenosha','531',['262'])],
'SC':[('Charleston','294',['843']),('Columbia','292',['803']),('Greenville','296',['864']),('Myrtle Beach','295',['843'])],
'OR':[('Portland','972',['503','971']),('Eugene','974',['541']),('Salem','973',['503']),('Gresham','970',['503']),('Bend','977',['541'])],
'LA':[('New Orleans','701',['504']),('Baton Rouge','708',['225']),('Shreveport','711',['318']),('Lafayette','705',['337']),('Metairie','700',['504'])],
'CT':[('Hartford','061',['860']),('New Haven','065',['203','475']),('Stamford','069',['203','475']),('Bridgeport','066',['203','475']),('Waterbury','067',['203'])],
'UT':[('Salt Lake City','841',['801','385']),('Provo','846',['801']),('Ogden','844',['801']),('West Valley City','841',['801']),('Sandy','840',['801'])]
}
CITY_WEIGHTS={s: np.array([.36,.22,.16,.12,.08,.06][:len(v)],dtype=float) for s,v in CITIES.items()}
for s in CITY_WEIGHTS: CITY_WEIGHTS[s] /= CITY_WEIGHTS[s].sum()

ETHNICITIES=np.array(['White (Non-Hispanic)','Hispanic/Latino','Black/African American (Non-Hispanic)','Asian (Non-Hispanic)','American Indian/Alaska Native (Non-Hispanic)','Native Hawaiian/Pacific Islander (Non-Hispanic)','Multiracial/Other (Non-Hispanic)'],dtype=object)
EDU=np.array(['Less than high school','High school diploma/GED','Some college - no degree','Associate degree','Bachelor degree','Master degree','Professional/Doctoral degree'],dtype=object)
INDUSTRIES=np.array(['Professional Scientific & Technical Services','Health Care & Social Assistance','Educational Services','Finance & Insurance','Manufacturing','Retail Trade','Accommodation & Food Services','Construction','Transportation & Warehousing','Public Administration','Information','Wholesale Trade','Real Estate & Rental','Other Services'],dtype=object)
IND_BASE=np.array([.11,.14,.09,.07,.09,.10,.07,.06,.06,.05,.04,.04,.03,.05])
IND_MULT={
'CA':{'Professional Scientific & Technical Services':1.35,'Information':1.50},'WA':{'Professional Scientific & Technical Services':1.45,'Information':1.45},'MA':{'Professional Scientific & Technical Services':1.35,'Health Care & Social Assistance':1.15},'CO':{'Professional Scientific & Technical Services':1.30},'UT':{'Professional Scientific & Technical Services':1.30,'Information':1.25},
'NY':{'Finance & Insurance':1.55,'Information':1.25},'NJ':{'Finance & Insurance':1.35,'Professional Scientific & Technical Services':1.20},'CT':{'Finance & Insurance':1.45},
'MD':{'Public Administration':1.50,'Professional Scientific & Technical Services':1.20},'VA':{'Public Administration':1.55,'Professional Scientific & Technical Services':1.20},
'MI':{'Manufacturing':1.55},'OH':{'Manufacturing':1.35},'IN':{'Manufacturing':1.55},'WI':{'Manufacturing':1.35},
'TX':{'Construction':1.20,'Manufacturing':1.15,'Professional Scientific & Technical Services':1.15},'LA':{'Construction':1.25,'Transportation & Warehousing':1.25},
'FL':{'Accommodation & Food Services':1.35,'Real Estate & Rental':1.25},'SC':{'Accommodation & Food Services':1.20,'Manufacturing':1.20},'TN':{'Manufacturing':1.20,'Transportation & Warehousing':1.15}
}
IND_INCOME=np.array([1.45,1.15,.95,1.40,1.00,.67,.55,1.00,.88,1.05,1.25,.90,1.10,.72])

# Region-aware religion model calibrated to Pew 2023-24 national profile, with synthetic state adjustments.
REL=np.array(['Protestant','Catholic','Latter-day Saint','Orthodox Christian','Other Christian','Jewish','Muslim','Buddhist','Hindu','Other religion','Religiously unaffiliated'],dtype=object)
REL_BASE=np.array([.40,.19,.02,.01,.02,.017,.012,.011,.009,.019,.29])
REGION={'CA':'West','TX':'South','FL':'South','NY':'Northeast','IL':'Midwest','PA':'Northeast','OH':'Midwest','NJ':'Northeast','GA':'South','MI':'Midwest','NC':'South','VA':'South','WA':'West','MA':'Northeast','AZ':'West','MD':'South','CO':'West','IN':'Midwest','TN':'South','MO':'Midwest','MN':'Midwest','WI':'Midwest','SC':'South','OR':'West','LA':'South','CT':'Northeast','UT':'West'}

def religion_weights(st):
    w=REL_BASE.copy()
    r=REGION[st]
    if r=='South': w*=np.array([1.30,1.00,.80,.70,1.05,.45,.80,.55,.45,.90,.72])
    elif r=='Northeast': w*=np.array([.80,1.35,.35,1.20,.85,1.80,1.10,.80,.90,.90,1.00])
    elif r=='West': w*=np.array([.78,.92,1.15,.85,.85,.75,1.00,1.25,1.35,1.10,1.22])
    else: w*=np.array([1.05,1.05,.95,.80,.95,.65,.85,.80,.75,.90,.98])
    if st=='UT': w*=np.array([.65,.45,18.0,.40,.65,.30,.35,.35,.30,.55,.60])
    if st in ('NY','NJ'): w[5]*=1.5
    if st=='LA': w[0]*=1.15; w[1]*=1.20
    return w/w.sum()
REL_W={s:religion_weights(s) for s in STATE_CODES}

# Synthetic names/street pools. Contact fields use reserved domains and fictional 555 exchange.
fake=Faker('en_US'); Faker.seed(SEED)
male_names=[]; female_names=[]; neutral_names=[]; last_names=[]; streets=[]
for _ in range(2500):
    male_names.append(fake.first_name_male().replace(',',''))
    female_names.append(fake.first_name_female().replace(',',''))
for _ in range(1200): neutral_names.append(fake.first_name().replace(',',''))
for _ in range(6000): last_names.append(fake.last_name().replace(',',''))
# Construct intentionally synthetic street names rather than copying real address records.
prefix=['Maple','Cedar','Oak','Pine','Willow','Lake','Hill','River','Sunset','Park','Meadow','Forest','Spring','Valley','North','South','West','East','Liberty','Heritage','Union','Grand','Highland','Ridge','Garden','Brook','Stone','Clearwater','Magnolia','Sycamore']
second=['View','Ridge','Grove','Point','Heights','Crossing','Run','Bend','Trail','Creek','Field','Gate','Park','Hollow','Terrace','Vista','Way','Landing','Commons','Square']
suffix=['St','Ave','Rd','Blvd','Ln','Dr','Ct','Way','Pkwy','Ter']
for a in prefix:
    for b in second[:10]:
        for c in suffix[:4]: streets.append(f'{a} {b} {c}')
for i in range(1200): streets.append(f'{prefix[i%len(prefix)]} {100+i%900} {suffix[i%len(suffix)]}')
male_names=np.array(male_names,dtype=object); female_names=np.array(female_names,dtype=object); neutral_names=np.array(neutral_names,dtype=object)
last_names=np.array(last_names,dtype=object); streets=np.array(streets,dtype=object)

# age bins and within-bin sampling
AGE_BINS=[(0,4),(5,17),(18,24),(25,34),(35,44),(45,54),(55,64),(65,74),(75,84),(85,94)]
MID_BASE=np.array([.091,.138,.129,.124,.127]) # 18-64 bins
YOUNG_SPLIT=np.array([.26,.74])
OLD_SPLIT=np.array([.57,.31,.12])

def age_weights(st):
    _,u18,o65,_,_,_,_=CFG[st]
    mid=1-u18-o65
    return np.r_[u18*YOUNG_SPLIT, mid*MID_BASE/MID_BASE.sum(), o65*OLD_SPLIT]
AGE_W={s:age_weights(s) for s in STATE_CODES}

def edu_probs(st):
    ba=CFG[st][4]
    hi=np.array([.62,.28,.10])*ba
    lo=np.array([.08,.32,.25,.12]); lo=lo/lo.sum()*(1-ba)
    return np.r_[lo,hi]
EDU_W={s:edu_probs(s) for s in STATE_CODES}

# State urban reference file
with open(STATE_REF,'w',encoding='utf-8',newline='') as f:
    f.write('urban_population_rank,state,state_code,2020_urban_population,2020_percent_urban,synthetic_sampling_weight,calibration_median_household_income,under18_target,age65plus_target,bachelors_plus_target,foreign_born_target\n')
    for i,s in enumerate(STATE_CODES,1):
        name,up,pct=URBAN[s]; med,u18,o65,fp,ba,fb,_=CFG[s]
        f.write(f'{i},{name},{s},{up},{pct:.4f},{STATE_P[i-1]:.8f},{med},{u18:.4f},{o65:.4f},{ba:.4f},{fb:.4f}\n')

headers=['person_id','first_name','last_name','gender','age','address_line_1','address_line_2','street','postal_code','city','state','country','phone_number','email','individual_yearly_income','marital_status','education','employment_status','resident_status','resident_type','family_member_count','number_of_children_in_family','number_of_adults_in_family','ethnicity','type_of_employment','occupation_industry','family_yearly_income','religion']

# Running validation counters
state_count=np.zeros(len(STATE_CODES),dtype=np.int64)
eth_count={x:0 for x in ETHNICITIES}
gender_count={'Male':0,'Female':0,'Non-binary/Other':0}
age_sum=0; income_sum=0; family_income_sum=0; employed=0; sample_lines=[]

start=time.time()
compressed_output=gzip.open(OUT,'wb',compresslevel=3)
compressed_output.write((','.join(headers)+'\n').encode('utf-8'))

for base in range(0,N_ROWS,CHUNK):
    n=min(CHUNK,N_ROWS-base)
    st_idx=rng.choice(len(STATE_CODES),size=n,p=STATE_P)
    state_count += np.bincount(st_idx,minlength=len(STATE_CODES))
    states=np.array([STATE_CODES[i] for i in st_idx],dtype=object)

    # allocate core arrays
    ages=np.empty(n,dtype=np.int16); genders=np.empty(n,dtype=object); ethn=np.empty(n,dtype=object)
    cities=np.empty(n,dtype=object); zips=np.empty(n,dtype=object); phones=np.empty(n,dtype=object)
    med_income=np.empty(n,dtype=float); ba_target=np.empty(n,dtype=float)
    resident_status=np.empty(n,dtype=object); resident_type=np.empty(n,dtype=object); religions=np.empty(n,dtype=object)
    education=np.empty(n,dtype=object); marital=np.empty(n,dtype=object); empstat=np.empty(n,dtype=object)
    type_emp=np.full(n,'Not applicable',dtype=object); industry=np.full(n,'Not applicable',dtype=object)

    for si,st in enumerate(STATE_CODES):
        ix=np.where(st_idx==si)[0]
        if not len(ix): continue
        m=len(ix); med,u18,o65,female,ba,foreign,race=CFG[st]
        med_income[ix]=med; ba_target[ix]=ba
        # Age by calibrated state bands
        bins=rng.choice(10,size=m,p=AGE_W[st])
        lo=np.array([AGE_BINS[b][0] for b in bins]); hi=np.array([AGE_BINS[b][1] for b in bins])
        ages[ix]=lo + (rng.random(m)*(hi-lo+1)).astype(np.int16)
        # Gender: small non-binary/other synthetic category, binary split anchored to female share
        nb=np.where(ages[ix]<13,.003,np.where(ages[ix]<25,.020,np.where(ages[ix]<45,.014,.006)))
        u=rng.random(m); female_cut=nb + (1-nb)*female
        gg=np.where(u<nb,'Non-binary/Other',np.where(u<female_cut,'Female','Male'))
        genders[ix]=gg
        # ethnicity
        rw=np.array(race,dtype=float); rw/=rw.sum(); ethn[ix]=rng.choice(ETHNICITIES,size=m,p=rw)
        # city / ZIP / fictional phone
        cp=CITY_WEIGHTS[st]; ci=rng.choice(len(CITIES[st]),size=m,p=cp)
        for cj in range(len(CITIES[st])):
            jx=ix[ci==cj]
            if not len(jx): continue
            city,prefix3,areas=CITIES[st][cj]
            cities[jx]=city
            zips[jx]=np.array([f'{prefix3}{x:02d}' for x in rng.integers(0,100,size=len(jx))],dtype=object)
            ac=rng.choice(areas,size=len(jx))
            # 555-0100 to 0199 is reserved for fictional use; duplicates intentional.
            last=rng.integers(100,200,size=len(jx))
            phones[jx]=np.array([f'+1-{a}-555-{x:04d}' for a,x in zip(ac,last)],dtype=object)
        # resident status anchored to foreign-born share
        rr=rng.random(m)
        # roughly half of foreign-born are naturalized; remaining split permanent/temporary-other
        resident_status[ix]=np.where(rr<1-foreign,'Citizen by birth',np.where(rr<1-foreign+foreign*.52,'Naturalized citizen',np.where(rr<1-foreign+foreign*.83,'Permanent resident','Temporary/other non-citizen')))
        # urban/suburban context (all records urban-population weighted)
        core=.47 + (URBAN[st][2]-80)/180
        core=float(np.clip(core,.40,.58)); inner=.34; outer=1-core-inner
        resident_type[ix]=rng.choice(['Urban core','Inner suburban','Outer suburban/peri-urban'],size=m,p=[core,inner,outer])
        religions[ix]=rng.choice(REL,size=m,p=REL_W[st])
        # education
        a=ages[ix]
        edu=np.empty(m,dtype=object)
        k=a<16; edu[k]=np.where(a[k]<5,'Not yet in school',np.where(a[k]<14,'Primary/Middle school','High school student'))
        k=(a>=16)&(a<18); edu[k]=rng.choice(['High school student','High school diploma/GED'],size=k.sum(),p=[.86,.14])
        k=(a>=18)&(a<25); edu[k]=rng.choice(['High school diploma/GED','Some college - no degree','Associate degree','Bachelor degree'],size=k.sum(),p=[.25,.42,.13,.20])
        k=a>=25; edu[k]=rng.choice(EDU,size=k.sum(),p=EDU_W[st])
        education[ix]=edu

    # marital status age-dependent
    u=rng.random(n)
    marital=np.full(n,'Never married',dtype=object)
    k=(ages>=18)&(ages<25)
    marital[k]=np.where(u[k]<.12,'Married',np.where(u[k]<.15,'Separated/Divorced','Never married'))
    k=(ages>=25)&(ages<35)
    marital[k]=np.where(u[k]<.49,'Married',np.where(u[k]<.59,'Separated/Divorced',np.where(u[k]<.60,'Widowed','Never married')))
    k=(ages>=35)&(ages<55)
    marital[k]=np.where(u[k]<.61,'Married',np.where(u[k]<.78,'Separated/Divorced',np.where(u[k]<.81,'Widowed','Never married')))
    k=(ages>=55)&(ages<70)
    marital[k]=np.where(u[k]<.58,'Married',np.where(u[k]<.75,'Separated/Divorced',np.where(u[k]<.88,'Widowed','Never married')))
    k=ages>=70
    marital[k]=np.where(u[k]<.44,'Married',np.where(u[k]<.56,'Separated/Divorced',np.where(u[k]<.86,'Widowed','Never married')))

    # household/family composition consistent counts
    adults=np.ones(n,dtype=np.int16); children=np.zeros(n,dtype=np.int16)
    married=marital=='Married'; adults[married]=2
    # Some multigenerational/rooming-family adults
    adults += (rng.random(n)<np.where(ages<25,.18,.08)).astype(np.int16)
    child_prob=np.where(ages<18,1.0,np.where((ages>=25)&(ages<45),.54,np.where((ages>=45)&(ages<55),.28,.06)))
    haskids=rng.random(n)<child_prob
    children[haskids]=1+rng.binomial(3,.33,size=haskids.sum()).astype(np.int16)
    # minors are part of a family with at least one adult; their row describes family composition, not just themselves
    children[ages<18]=np.maximum(children[ages<18],1)
    adults[ages<18]=np.maximum(adults[ages<18],1 + (rng.random((ages<18).sum())<.72).astype(np.int16))
    family_count=adults+children
    # small cap for realism
    over=family_count>8
    children[over]=np.maximum(0,8-adults[over]); family_count=adults+children

    # Employment status by age and education; state income does not directly force employment.
    u=rng.random(n)
    empstat=np.full(n,'Not in labor force',dtype=object)
    empstat[ages<16]='Minor / not in labor force'
    k=(ages>=16)&(ages<19)
    empstat[k]=np.where(u[k]<.24,'Employed part-time',np.where(u[k]<.30,'Employed full-time',np.where(u[k]<.83,'Student',np.where(u[k]<.88,'Unemployed - seeking work','Not in labor force'))))
    k=(ages>=19)&(ages<25)
    empstat[k]=np.where(u[k]<.41,'Employed full-time',np.where(u[k]<.63,'Employed part-time',np.where(u[k]<.78,'Student',np.where(u[k]<.84,'Unemployed - seeking work','Not in labor force'))))
    k=(ages>=25)&(ages<55)
    empstat[k]=np.where(u[k]<.72,'Employed full-time',np.where(u[k]<.83,'Employed part-time',np.where(u[k]<.88,'Unemployed - seeking work',np.where(u[k]<.93,'Homemaker/Caregiver','Not in labor force'))))
    k=(ages>=55)&(ages<65)
    empstat[k]=np.where(u[k]<.61,'Employed full-time',np.where(u[k]<.70,'Employed part-time',np.where(u[k]<.74,'Unemployed - seeking work',np.where(u[k]<.88,'Retired','Not in labor force'))))
    k=(ages>=65)&(ages<75)
    empstat[k]=np.where(u[k]<.20,'Employed full-time',np.where(u[k]<.28,'Employed part-time',np.where(u[k]<.86,'Retired','Not in labor force')))
    k=ages>=75
    empstat[k]=np.where(u[k]<.05,'Employed full-time',np.where(u[k]<.09,'Employed part-time',np.where(u[k]<.91,'Retired','Not in labor force')))
    employed_mask=np.isin(empstat,['Employed full-time','Employed part-time'])

    # employment class and broad occupation industry
    ue=rng.random(n)
    type_emp[employed_mask]=np.where(ue[employed_mask]<.73,'Private sector',np.where(ue[employed_mask]<.84,'Government',np.where(ue[employed_mask]<.90,'Nonprofit',np.where(ue[employed_mask]<.98,'Self-employed','Gig/contract'))))
    for si,st in enumerate(STATE_CODES):
        ix=np.where((st_idx==si)&employed_mask)[0]
        if not len(ix): continue
        w=IND_BASE.copy()
        for ind,mult in IND_MULT.get(st,{}).items(): w[np.where(INDUSTRIES==ind)[0][0]]*=mult
        w/=w.sum(); industry[ix]=rng.choice(INDUSTRIES,size=len(ix),p=w)

    # Individual income model
    edu_mult=np.ones(n)
    edu_map={'Not yet in school':0,'Primary/Middle school':0,'High school student':.35,'Less than high school':.55,'High school diploma/GED':.72,'Some college - no degree':.86,'Associate degree':.98,'Bachelor degree':1.28,'Master degree':1.58,'Professional/Doctoral degree':2.15}
    for k,v in edu_map.items(): edu_mult[education==k]=v
    age_mult=np.where(ages<18,.12,np.where(ages<25,.55,np.where(ages<35,.90,np.where(ages<45,1.10,np.where(ages<55,1.20,np.where(ages<65,1.12,np.where(ages<75,.78,.55)))))))
    state_factor=med_income/83730.0
    ind_mult=np.ones(n)
    for i,name in enumerate(INDUSTRIES): ind_mult[industry==name]=IND_INCOME[i]
    base_income=52000*state_factor*age_mult*np.maximum(edu_mult,.25)*ind_mult
    noise=rng.lognormal(mean=0,sigma=.46,size=n)
    individual=base_income*noise
    individual[empstat=='Employed part-time']*=.48
    individual[empstat=='Student']*=rng.uniform(0,.18,size=(empstat=='Student').sum())
    individual[empstat=='Minor / not in labor force']*=rng.uniform(0,.05,size=(empstat=='Minor / not in labor force').sum())
    individual[empstat=='Homemaker/Caregiver']*=rng.uniform(0,.10,size=(empstat=='Homemaker/Caregiver').sum())
    individual[empstat=='Not in labor force']*=rng.uniform(0,.12,size=(empstat=='Not in labor force').sum())
    individual[empstat=='Unemployed - seeking work']*=rng.uniform(.02,.20,size=(empstat=='Unemployed - seeking work').sum())
    individual[empstat=='Retired']=rng.lognormal(np.log(30000*state_factor[empstat=='Retired']),.50)
    # rare high-income tail
    tail=(rng.random(n)<.004)&employed_mask
    individual[tail]*=rng.uniform(2.2,6.0,size=tail.sum())
    individual=np.clip(individual,0,2500000)
    individual=np.round(individual/100)*100

    # Family income: correlated with state median, adults, education, individual income and marital status.
    fam_base=med_income*1.12*(.72+.28*np.sqrt(adults))*(.95+.06*np.minimum(children,3))
    fam=fam_base*rng.lognormal(mean=-.08,sigma=.48,size=n)
    fam=np.maximum(fam,individual + np.maximum(0,adults-1)*rng.lognormal(np.log(np.maximum(12000,state_factor*30000)),.55,size=n))
    fam=np.clip(fam,0,4000000); fam=np.round(fam/100)*100

    # Names and synthetic address
    fi_m=rng.integers(0,len(male_names),size=n); fi_f=rng.integers(0,len(female_names),size=n); fi_n=rng.integers(0,len(neutral_names),size=n)
    first=np.where(genders=='Male',male_names[fi_m],np.where(genders=='Female',female_names[fi_f],neutral_names[fi_n]))
    last=last_names[rng.integers(0,len(last_names),size=n)]
    street=streets[rng.integers(0,len(streets),size=n)]
    house=rng.integers(1,9999,size=n)
    addr1=np.array([f'{h} {s}' for h,s in zip(house,street)],dtype=object)
    ua=rng.random(n); aptnum=rng.integers(1,999,size=n)
    addr2=np.where(ua<.24,np.array([f'Apt {x}' for x in aptnum],dtype=object),np.where(ua<.32,np.array([f'Unit {x}' for x in aptnum],dtype=object),''))

    # IDs/email guaranteed synthetic using IANA-reserved example domains.
    ids=np.arange(ID_OFFSET+base+1,ID_OFFSET+base+n+1,dtype=np.int64)
    person=np.array([f'US{v:09d}' for v in ids],dtype=object)
    domains=np.array(['example.com','example.net','example.org'],dtype=object)
    dom=domains[ids%3]
    email=np.array([f'person{v:09d}@{d}' for v,d in zip(ids,dom)],dtype=object)

    # Build/write chunk. Values intentionally avoid commas/newlines to keep fast CSV serialization valid.
    lines=[]; append=lines.append
    for i in range(n):
        append(','.join((person[i],str(first[i]),str(last[i]),str(genders[i]),str(int(ages[i])),addr1[i],str(addr2[i]),str(street[i]),str(zips[i]),str(cities[i]),str(STATE_NAMES[st_idx[i]]),'United States',str(phones[i]),email[i],str(int(individual[i])),str(marital[i]),str(education[i]),str(empstat[i]),str(resident_status[i]),str(resident_type[i]),str(int(family_count[i])),str(int(children[i])),str(int(adults[i])),str(ethn[i]),str(type_emp[i]),str(industry[i]),str(int(fam[i])),str(religions[i]))))
    block=('\n'.join(lines)+'\n').encode('utf-8')
    compressed_output.write(block)

    if base==0:
        sample_lines=lines[:10000]
        with open(SAMPLE,'w',encoding='utf-8',newline='') as sf:
            sf.write(','.join(headers)+'\n'); sf.write('\n'.join(sample_lines)+'\n')

    # counters
    age_sum += int(ages.sum()); income_sum += float(individual.sum()); family_income_sum += float(fam.sum()); employed += int(employed_mask.sum())
    vals,cnts=np.unique(genders,return_counts=True)
    for v,c in zip(vals,cnts): gender_count[str(v)]+=int(c)
    vals,cnts=np.unique(ethn,return_counts=True)
    for v,c in zip(vals,cnts): eth_count[str(v)]+=int(c)

    done=base+n; elapsed=time.time()-start
    print(f'PROGRESS {done}/{N_ROWS} rows ({done/N_ROWS:.1%}) elapsed={elapsed:.1f}s',flush=True)

compressed_output.close()

summary={
 'rows':N_ROWS,'columns':len(headers),'seed':SEED,'id_offset':ID_OFFSET,'id_start':ID_OFFSET+1,'id_end':ID_OFFSET+N_ROWS,'file':str(OUT),'file_size_bytes':OUT.stat().st_size,
 'mean_age':age_sum/N_ROWS,'mean_individual_yearly_income':income_sum/N_ROWS,'mean_family_yearly_income':family_income_sum/N_ROWS,
 'employed_share':employed/N_ROWS,'gender_distribution':{k:v/N_ROWS for k,v in gender_count.items()},
 'ethnicity_distribution':{k:v/N_ROWS for k,v in eth_count.items()},
 'state_distribution':{STATE_CODES[i]:{'state':URBAN[STATE_CODES[i]][0],'rows':int(state_count[i]),'share':float(state_count[i]/N_ROWS)} for i in range(len(STATE_CODES))},
 'contact_safety':'Emails use IANA-reserved example.com/example.net/example.org domains. Phones use the fictional 555-0100..0199 exchange range. Addresses are algorithmically synthesized, not copied from address records.',
 'methodology':'State selection and row weights follow Census 2020 urban population counts for the top 27 states. Demographic/economic fields are correlated synthetic draws calibrated to broad recent ACS/QuickFacts-style state parameters. Religion is survey-calibrated synthetic data based on Pew 2023-24 national/regional patterns, because the Census does not collect religion.',
 'source_urls':['https://www2.census.gov/geo/docs/reference/ua/State_Urban_Rural_Pop_2020_2010.xlsx','https://www.census.gov/programs-surveys/acs/data/data-via-api.html','https://www.census.gov/quickfacts/','https://www.pewresearch.org/religious-landscape-study/']
}
with open(SUMMARY,'w',encoding='utf-8') as f: json.dump(summary,f,indent=2)
print(f'DONE {OUT} size={OUT.stat().st_size/1024/1024:.1f} MiB elapsed={time.time()-start:.1f}s',flush=True)
