import pandas as pd
import sys
import os

def find_import_files(inputs):
    
    # Find the import files.
    import_files = [
        file for file in os.listdir(inputs['Import location']) if
        file.lower().endswith(".csv") and not file.startswith("~$")
    ]
    return(import_files)

def import_data(inputs):
    
    # Import the raw FED file.
    import_destination = os.path.join(inputs['Import location'], inputs['Filename'])
    df = pd.read_csv(import_destination)
    
    return(df)

def clean_data(df, inputs, print_message=True):
    
    # Clean the dataframe.  
    df = df.dropna(how='all')
    df.index = list(range(len(df)))
    df.columns = df.columns.str.replace(' ', '')
    df.columns = df.columns.str.replace('FR_Ratio', 'Session_Type')
    df.columns = df.columns.str.replace('Session_type', 'Session_Type')
    df.columns = df.columns.str.replace('InterPelletInterval', 'Interpellet_Interval')
    df['Retrieval_Time'] = df['Retrieval_Time'].replace('Timed_out', 60)
    df = df.drop(columns=['FED_Version', 'Device_Number', 'Battery_Voltage'],errors="ignore")
    df.columns = df.columns.str.replace('_', ' ')
    
    # Check whether the last row has been cut off and exclude if needed.
    if df.columns[-1] == "Poke Time":
        
        # Import the file again, but without converting "nan" to np.nan.
        import_destination = os.path.join(inputs['Import location'], inputs['Filename'])
        raw = pd.read_csv(import_destination, keep_default_na=False)
        raw = raw.dropna(how='all')
        raw.index = list(range(len(raw)))
        raw.columns = raw.columns.str.replace(' ', '')
        raw.columns = raw.columns.str.replace('_', ' ')
        
        # If the last value is not a number or "nan", exclude that row.
        last_value = raw["Poke Time"].iloc[-1]
        if last_value in ["","n","na"]:
            last_index = df.index[-1]
            df = df.drop(last_index)
            if print_message:
                print(f"\n\nThe last row of {inputs['Filename']} is cut off, "+
                      "so this row has been dropped from the analysis.\n")
    
    # Now make the retrieval time column numeric.
    df['Retrieval Time'] = df['Retrieval Time'].apply(pd.to_numeric)
    
    return(df)

def replace_values(val,new_val):
    return(new_val)

def remove_prefix(val):
    return(int(val[2:]))

def correct_session_type_columns(df, inputs):
    
    # Correct the session type columns.
    # Numbers that form part of the Progressive Ratio.
    # https://pubmed.ncbi.nlm.nih.gov/8794935/
    PR_nums = [0,1,2,4,6,9,12,15,20,25,32,40,50,62,77,95,118,145,178,219,
               268,328,402,492,603,737,901,1102,1347,1646,2012,2459,3004]
    
    # If there is a 'Session Type' and an 'FR' column.
    if 'Session Type' in df.columns and 'FR' in df.columns:
        
        if df['Session Type'].iloc[0][:2] == 'FR':
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val='Fixed ratio')
        elif df['Session Type'].iloc[0][:2] == 'PR':
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val='Progressive ratio')
        elif df['Session Type'].iloc[0] == 'Menu':
            unique_values = list(df['FR'].unique())
            if len(unique_values) == 1:
                name = 'Fixed ratio'
            elif all([val in PR_nums for val in unique_values]):
                name = 'Progressive ratio'
            else:
                name = 'Unnamed ratio'
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val=name)

    # If there is only a 'Session Type' column.
    if 'Session Type' in df.columns and 'FR' not in df.columns:

        if str(df['Session Type'].iloc[0])[:2] == 'FR':
            df['FR']           = df['Session Type'].apply(remove_prefix)
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val='Fixed ratio')
        elif str(df['Session Type'].iloc[0])[:2] == 'PR':
            df['FR']           = df['Session Type'].apply(remove_prefix)
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val='Progressive ratio')
        elif str(df['Session Type'].iloc[0]).isdigit():
            unique_values = list(df['Session Type'].unique())
            if len(unique_values) == 1:
                name = 'Fixed ratio'
            elif all([val in PR_nums for val in unique_values]):
                name = 'Progressive ratio'
            else:
                name = 'Unnamed ratio'
            df['FR']           = df['Session Type'].copy()
            df['Session Type'] = df['Session Type'].apply(replace_values, new_val=name)
    
    inputs["Session Type"] = df.at[0,"Session Type"]
            
    return(df, inputs)

def combine_time_columns(df, inputs):
    
    # Combine time columns if there are 2.
    if "MM:DD:YYYYhh:mm:ss" not in df.columns:
        df["MM:DD:YYYY"] = df["MM:DD:YYYY"] + " " + df["hh:mm:ss"]
        df = df.rename(columns={"MM:DD:YYYY": "Time"})
        df = df.drop(columns=['hh:mm:ss'])
    else:
        df = df.rename(columns={"MM:DD:YYYYhh:mm:ss": "Time"})
    
    # Remove any rows with null dates.
    # "0/0/" means the day and month are zero.
    rows_without_null_dates = df["Time"].str.contains("0/0/")==False
    df = df[rows_without_null_dates]
    df.index = list(range(len(df)))
    
    # Convert the values to the datetime format.
    df["Time"] = pd.to_datetime(df["Time"])

    # Check that the time column is monotonically increasing.
    if df["Time"].is_monotonic_increasing == False:
        print(f'\nThe time column for {inputs["Filename"]} decreases at some point.')
        sys.exit()

    return(df)

def find_date(time):
    return(time.date())

def edit_start_and_end_times(df, inputs):
    
    # Find the start and end times, if use initiation poke or use first/last 
    # timestamps is selected.          
    for time in ['Start time', 'End time']:
        
        if inputs[time+' type'] == 'Use custom time':
            # Find a way to identify when there is only a time listed and no date.
            # This is tricky and I may update this in the future.
            # If a date isn't included, use the most common date from the FED file.
            date_time_components = str(inputs[time]).split(' ')
            date_time_components = [val for val in date_time_components if val!='']
            if len(date_time_components) == 1:
                most_common_date = df["Time"].apply(find_date).mode()[0]
                inputs[time] = str(most_common_date)+' '+inputs[time]
            
            # Convert the string to a datetime object.
            inputs[time] = pd.to_datetime(inputs[time])
        
        if time == 'Start time':
            if inputs[time+' type'] == 'Use first timestamp':
                inputs[time] = df.at[0,"Time"]
        
            if inputs[time+' type'] == 'Use initiation poke':
                for i in range(len(df)):
                    active_poke_col = df.at[i,"Active Poke"] + " Poke Count"
                    if df.at[i,active_poke_col] >= 1:
                        inputs[time] = df.at[i,"Time"]
                        break
                    
        if time == 'End time':
            if inputs[time+' type'] == 'Use last timestamp':
                inputs[time] = df.at[len(df)-1,"Time"]
        
    # If the end time is before the first data point or the start time is after 
    # the last data point, throw an error.
    if inputs['End time'] < df.at[0,"Time"]:
        print('\nThe end time is before the first data point in file '+inputs['Filename']+'.')
        print('Change the custom end time or select "Use last end time".')
        sys.exit()
    elif inputs['Start time'] > df.at[len(df)-1,"Time"]:
        print('\nThe start time is after the last data point in file '+inputs['Filename']+'.')
        print('Change the custom start time, select "Use first timestamp" or '+
              'select "Use initiation poke".')
        sys.exit()
        
    return(inputs)

def remove_data_outside_window(df, inputs):
    
    # Remove the data before the start time and after the end time.
    del_indices = []
    for i in range(len(df)):
        if df.at[i,"Time"] < inputs['Start time']:
            del_indices.append(i)
        if df.at[i,"Time"] > inputs['End time']:
            del_indices.append(i)
    df = df.drop(del_indices)
    df.index = list(range(len(df)))
    
    return(df)

def add_additional_columns_stopsig(df):
    
    # There are some events that would be useful to summarise as separate 
    # cumulative columns for the stopsig task.
    list_events = [">Left_Regular_trial",">Left_Stop_trial","LeftinTimeOut",
                   "NoPoke_Regular_(incorrect)","NoPoke_STOP_(correct)","Pellet",
                   "Right_no_left","Right_Regular_(correct)","RightDuringDispense",
                   "RightinTimeout"]
    for event in list_events:
        df[event] = (df['Event'] == event).cumsum()
            
    return(df)

def check_for_incomplete_closedecon_data(df, inputs):
    
    # Check whether the block pellet count is monotonically increasing.
    # This means there is only 1 block and it is incomplete.
    # To exclude this from the special closed economy analysis, change the session type. 
    if df["Block Pellet Count"].is_monotonic_increasing:
        inputs["Session Type"] = "Incomplete_ClosedEcon"
        df["Session Type"] = "Incomplete_ClosedEcon"
        print(f"\n\n{inputs['Filename']} has been excluded from the closed economy analysis "+
              "because there is only 1 block and it is incomplete.\n")
    
    return(df, inputs)

def preprocess_data(inputs):
    
    # Import the raw data.
    df = import_data(inputs)
    
    # Clean the data.
    df = clean_data(df, inputs)
    
    # Correct session type columns.
    df, inputs = correct_session_type_columns(df, inputs)
    
    # Combine time columns if there are 2.
    df = combine_time_columns(df, inputs)
    
    # Edit the start and end times.
    inputs = edit_start_and_end_times(df, inputs)
    
    # Remove the data before the start time and after the end time.
    df = remove_data_outside_window(df, inputs)
    
    if inputs["Session Type"] == "StopSig":
        # Add additional columns based on the events column for the stopsig task.
        df = add_additional_columns_stopsig(df)
    
    if inputs["Session Type"] == "ClosedEcon_PR1":
        # Rename session type if there is only 1 block of incomplete data.
        df, inputs = check_for_incomplete_closedecon_data(df, inputs)
    
    return(df, inputs)
