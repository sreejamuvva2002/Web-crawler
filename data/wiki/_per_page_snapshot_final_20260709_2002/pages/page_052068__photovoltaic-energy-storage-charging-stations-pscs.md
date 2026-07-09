---
title: "Photovoltaic Energy Storage Charging Stations (PSCS)"
entity_type: charging_infrastructure
supply_chain_category: charging_infrastructure
page_id: page_052068
publication_date: 
source_url: https://www.electric-vehicle.org/optimizing-energy-storage-for-solar-powered-ev-charging-stations/
generated_from: v15 single-page extraction (pre Stage-6 merge)
---

# Photovoltaic Energy Storage Charging Stations (PSCS)

**Type:** charging_infrastructure  ·  **Role:** charging_infrastructure  ·  **Published:** ?

**Source:** [Optimizing Energy Storage for Solar-Powered EV Charging Stations – Electric-Vehicle.org](https://www.electric-vehicle.org/optimizing-energy-storage-for-solar-powered-ev-charging-stations/)  ·  `page_052068`

## Facts

- Global EV adoption is surging, driving demand for charging infrastructure that aligns with environmental and economic goals.
- Photovoltaic energy storage charging stations (PSCS) integrate solar power generation, energy storage, and EV charging into a single system.
- A study published in Zhejiang Electric Power presents a novel approach to optimizing PSCS energy storage capacity by accounting for user charging behavior and PV uncertainty.
- The research was led by Jiang Yu from the School of Electric Power Engineering at Nanjing Institute of Technology.
- Co-authors include Lü Ganyun, Jia Dexiang from State Grid Energy Research Institute Co., Ltd., and Yu Xiangyi, Shan Tingting, Yu Ming, and Wu Qiyu from State Grid Jiangsu Electric Power Co., Ltd.
- The study addresses balancing cost, reliability, and sustainability for renewable-powered charging infrastructure amid unpredictable solar generation and fluctuating demand.
- China's government aims for peak carbon emissions by 2030 and carbon neutrality by 2060, catalyzing investments in clean energy technologies like PSCS.
- PSCS uses on-site solar panels to generate power, stores excess energy in batteries, and supplies it to EVs during high demand or low solar output.
- Proper sizing of the energy storage system is critical; oversizing increases capital expenditure, while undersizing compromises reliability and revenue potential.
- Traditional optimization models rely on average PV output data, failing to capture solar variability due to weather fluctuations, cloud cover, and seasonal changes.
- Traditional models also overlook dynamic EV user behavior influenced by daily travel patterns, temperature, and pricing incentives.
- The researchers used an improved K-means clustering algorithm to generate representative PV output scenarios from a full year of historical solar data from a city in southern China.
- The improved K-means modifies initial cluster center selection using maximum distance and uses a Gaussian kernel function instead of Euclidean distance for similarity measurement.
- This approach identified three distinct PV output patterns, each associated with a specific probability of occurrence.
- The team evaluated clustering quality using the silhouette coefficient; the improved K-means achieved a score of 0.628, outperforming traditional K-means (0.478) and K-means++ (0.598).
- EVs were categorized into three types with distinct usage patterns: buses follow fixed routes and schedules requiring predictable charging windows, taxis operate for extended hours charging twice daily, and private cars exhibit flexible behavior often charging after work or on weekends.
- The model incorporated data on daily mileage, departure times, and battery specifications; private cars were assumed to travel an average of 70 kilometers per day with a per-kilometer energy consumption of 0.149 kWh under standard conditions.
- A cubic polynomial function was used to describe the relationship between ambient temperature and EV energy consumption based on empirical data.
- The model accounted for air conditioning load during driving, which varies with speed and climate.
- The Monte Carlo method was employed to handle stochastic driving and charging decisions by running thousands of simulations sampling departure times and mileages according to statistical distributions like log-normal for mileage.
- Demand response using price signals was incorporated to influence consumer behavior and shift private car charging away from peak hours, reducing strain on the grid.
- Time-of-use pricing structures were optimized to incentivize charging when solar generation is high or grid prices are low, maximizing PV self-consumption and minimizing reliance on expensive grid power.
- A price elasticity matrix quantified how changes in charging prices affect load distribution across different time slots, including self-elasticity and cross-elasticity.
- Dynamic pricing for private car owners flattened the overall load curve, decreasing peak demand and increasing off-peak consumption to reduce operational costs and enhance grid stability.
- The economic model included carbon emissions based on the grid's hourly emission factor to reflect true electricity costs and encourage minimizing grid purchases during high-emission periods.
- The optimization objective function minimizes total daily cost, which includes grid electricity purchase cost, carbon emission cost, operation and maintenance expenses, revenue from selling excess solar power to the grid, and revenue from charging EVs.
- A case study validated the approach on a residential-area PSCS with a 350 kW PV installation and a maximum charging power of 100 kW.
- Five configurations were compared using MATLAB and the CPLEX solver: no PV/no demand response, typical PV/no demand response, typical PV/with demand response, multi-scenario PV/no demand response, and multi-scenario PV/with demand response.
- The optimal energy storage capacity for the multi-scenario PV with demand response scenario was calculated to be 461 kWh, yielding a daily profit of 4,334.17 yuan.
- Systems using typical PV data required either more storage at 496 kWh or delivered lower profits at 4,218.21 yuan, highlighting the inefficiency of oversimplified models.
- The multi-scenario PV with demand response scenario achieved the lowest daily CO₂ emissions at 8,218 kg, compared to over 9,300 kg in the baseline case without solar.
- Enabling price-based load shifting increased daily revenue by over 100 yuan and reduced emissions by nearly 300 kg compared to the same PV model without demand response.
- The study suggests extending the model to include vehicle-to-grid capabilities, allowing EVs themselves to act as distributed energy resources to enhance grid flexibility and open new revenue streams.
