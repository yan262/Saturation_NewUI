/**
  ******************************************************************************
  * @file          : app_tof.c
  * @author        : IMG SW Application Team
  * @brief         : This file provides code for the configuration
  *                  of the STMicroelectronics.X-CUBE-TOF1.3.4.3 instances.
  ******************************************************************************
  *
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "app_tof.h"
#include "main.h"
#include <stdio.h>

#include "53l8a1_ranging_sensor.h"
#include "app_tof_pin_conf.h"
#include "custom.h"

/* Private typedef -----------------------------------------------------------*/

extern double sat;

/* Private define ------------------------------------------------------------*/
#define TIMING_BUDGET (20U) /* 5 ms < TimingBudget < 100 ms */
#define RANGING_FREQUENCY (40U) /* Ranging frequency Hz (shall be consistent with TimingBudget value) */
#define POLLING_PERIOD (20U) /* refresh rate for polling mode (milliseconds) */

/* Private variables ---------------------------------------------------------*/
static RANGING_SENSOR_ProfileConfig_t Profile;
static RANGING_SENSOR_Result_t Result;
static int32_t status = 0;
static uint8_t ToF_Present[RANGING_SENSOR_INSTANCES_NBR] = {0};
volatile uint8_t ToF_EventDetected = 0;

static const char *TofDevStr[] =
{
  [VL53L8A1_DEV_LEFT] = "LEFT",
  [VL53L8A1_DEV_CENTER] = "CENTER",
  [VL53L8A1_DEV_RIGHT] = "RIGHT"
};

///////////////////////////////////
/* ?????????? Private variables ???????? */
static int16_t BaseMap_L[64] = {110, 110, 110, 110, 110, 110, 110, 110, 
                                110, 115, 111, 107, 108, 109, 110, 110, 
                                123, 115, 106, 102, 103, 106, 107, 110, 
                                128, 114, 102, 93, 96, 101, 104, 106, 
                                130, 114, 100, 84, 80, 94, 101, 103, 
                                121, 111, 100, 98, 96, 99, 102, 109, 
                                110, 109, 104, 100, 100, 102, 104, 110, 
                                110, 110, 104, 100, 103, 105, 110, 110}; // 闁告凹鍨版慨鈺呭籍閹澘娈伴柛鏂诲妽閻楀酣宕欓崱妤€袟闁诡兛绀侀敐鐐哄礂閿燂拷
static int16_t BaseMap_R[64] = {110, 110, 110, 110, 110, 110, 110, 110, 
                                110, 110, 104, 102, 103, 106, 110, 110, 
                                110, 102, 97, 96, 98, 101, 114, 110, 
                                108, 99, 94, 73, 87, 96, 116, 134, 
                                110, 101, 97, 92, 93, 101, 114, 110, 
                                110, 105, 99, 97, 99, 103, 110, 110, 
                                110, 110, 110, 103, 102, 110, 110, 110, 
                                110, 110, 110, 110, 110, 110, 110, 110}; // 闁告凹鍨版慨鈺呭籍閹澘娈伴柛鏂诲妽閻楀酣宕欓崱妤€袟闁诡兛绀侀敐鐐哄礂閿燂拷
static uint8_t Is_Calibrated = 1;   // 0閻炴稏鍔庨妵姘变焊濮橆厽寮撻柡宥佲偓鍐叉珯闁挎稑鐭傚〒鍓佹嫚鐠囨彃绲跨紒宀€鍎よ棢闁哄鍩栭弳鐔煎箲閿燂拷


static const float CosMap[64] = 
{
    0.93, 0.95, 0.97, 0.98, 0.98, 0.97, 0.95, 0.93,
    0.95, 0.97, 0.98, 0.99, 0.99, 0.98, 0.97, 0.95,
    0.97, 0.98, 0.99, 1.00, 1.00, 0.99, 0.98, 0.97,
    0.98, 0.99, 1.00, 1.00, 1.00, 1.00, 0.99, 0.98,
    0.98, 0.99, 1.00, 1.00, 1.00, 1.00, 0.99, 0.98,
    0.97, 0.98, 0.99, 1.00, 1.00, 0.99, 0.98, 0.97,
    0.95, 0.97, 0.98, 0.99, 0.99, 0.98, 0.97, 0.95,
    0.93, 0.95, 0.97, 0.98, 0.98, 0.97, 0.95, 0.93
};


/* ??????????闁跨喐鏋婚幏锟????????闁跨喐鏋婚幏锟?? */
#define NOISE_THRESHOLD 8     // ??????????? (mm)
#define TRAY_FULL_HEIGHT 100  // ????????? (mm)



/* Private function prototypes -----------------------------------------------*/
static void MX_53L8A1_MultiSensorRanging_Init(void);
static void MX_53L8A1_MultiSensorRanging_Process(void);

static void print_result(RANGING_SENSOR_Result_t *Result);
static void write_lowpower_pin(uint8_t device, GPIO_PinState pin_state);
static void reset_all_sensors(void);
static void print_merged_result(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R);
static void _sort_8(int16_t *arr);
void Process_16Columns_Robust(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R, float *out_heights);
static void print_compensated_height_matrix(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R);
float Calculate_Tray_Saturation(float *col_heights);
void Serial_Output_For_Python(float *cols, float sat);

void MX_TOF_Init(void)
{
  /* USER CODE BEGIN SV */

  /* USER CODE END SV */

  /* USER CODE BEGIN TOF_Init_PreTreatment */

  /* USER CODE END TOF_Init_PreTreatment */

  /* Initialize the peripherals and the TOF components */

  MX_53L8A1_MultiSensorRanging_Init();

  /* USER CODE BEGIN TOF_Init_PostTreatment */

  /* USER CODE END TOF_Init_PostTreatment */
}

/*
 * LM background task
 */
void MX_TOF_Process(void)
{
  /* USER CODE BEGIN TOF_Process_PreTreatment */

  /* USER CODE END TOF_Process_PreTreatment */

  MX_53L8A1_MultiSensorRanging_Process();

  /* USER CODE BEGIN TOF_Process_PostTreatment */

  /* USER CODE END TOF_Process_PostTreatment */
}

static void MX_53L8A1_MultiSensorRanging_Init(void)
{
  uint8_t device;
  uint16_t i2c_addr;
  uint32_t id;

  /* Initialize Virtual COM Port */
  BSP_COM_Init(COM1);

  printf("53L8A1 Multi Sensor Ranging demo application\n");

  reset_all_sensors();

  /* Turn off all the sensors */
  for (device = 0; device < RANGING_SENSOR_INSTANCES_NBR; device++)
  {
    write_lowpower_pin(device, GPIO_PIN_RESET);
  }

  /* initializes each device and put it in low power mode */
  for (device = 0; device < RANGING_SENSOR_INSTANCES_NBR; device++)
  {
    /* enable only one sensor */
    write_lowpower_pin(device, GPIO_PIN_SET);
    HAL_Delay(2);

	  printf("Initialize sensor %s\n", TofDevStr[device]);
    status = VL53L8A1_RANGING_SENSOR_Init(device);

    if (status != BSP_ERROR_NONE)
    {
      printf("VL53L8A1_RANGING_SENSOR_Init %d failed\n", device);
      ToF_Present[device] = 0; /* device not detected */
    }
    else
    {
      ToF_Present[device] = 1; /* device detected */
    }
    // ???? ID ?????????
      //VL53L8A1_RANGING_SENSOR_ReadID(device, &id);
      // printf("ToF sensor %d - ID: %04lX\n", device, (unsigned long)id);

    write_lowpower_pin(device, GPIO_PIN_RESET); /* turn off the device */
  }

  /* power on the devices one at a time and change their address
   * once the address is updated, the communication with the devices is checked
   * reading its ID.
   */
  for (device = 0; device < RANGING_SENSOR_INSTANCES_NBR; device++)
  {
    /* skip the sensor if init not successful */
    if (ToF_Present[device] == 0) { continue; }

    /* turn on the device */
    write_lowpower_pin(device, GPIO_PIN_SET);

    /* left: 0x54, center: 0x56, right: 0x58 */
    i2c_addr = (RANGING_SENSOR_VL53L8CX_ADDRESS + (device + 1) * 2);
	  printf("Set sensor %s I2C address to 0X%x\n", TofDevStr[device], i2c_addr);
    VL53L8A1_RANGING_SENSOR_SetAddress(device, i2c_addr);

    /* check the communication with the device reading the ID */
    VL53L8A1_RANGING_SENSOR_ReadID(device, &id);
    printf("ToF sensor %d - ID: %04lX\n", device, (unsigned long)id);
  }
}




/* ?????????? app_tof.c ????????????????闁跨喐鏋婚幏锟????????????????/??????? */
extern double sat;               // ???? main.c ?闁跨喐鏋婚幏锟???????????????
static uint8_t sensors_started = 0; // ???????????????闁跨喐鏋婚幏锟?
static RANGING_SENSOR_ProfileConfig_t Profile; // ?????????????


/**
  * @brief  ????????????????????
  * @note   ???????? while(1)???? main.c ?? while(1) ???????
  */
static void MX_53L8A1_MultiSensorRanging_Process(void)
{
  uint8_t i;
  int32_t status;
  static RANGING_SENSOR_Result_t Result_L;
  static RANGING_SENSOR_Result_t Result_R;
  uint8_t has_L = 0;
  uint8_t has_R = 0;
  float feature_columns[16];

  // --- 1. ????/???????? (???????闁跨喐鏋婚幏锟???????) ---
  if (sensors_started == 0) 
  {
    // ???闁跨喐鏋婚幏锟???
    Profile.RangingProfile = RS_PROFILE_8x8_CONTINUOUS;
    Profile.TimingBudget = 20;    // ???????? TIMING_BUDGET ???????
    Profile.Frequency = RANGING_FREQUENCY;       // ???????? RANGING_FREQUENCY ???????
    Profile.EnableAmbient = 0;
    Profile.EnableSignal = 0;

    printf("Starting Sensors...\n");
    for (i = 0; i < RANGING_SENSOR_INSTANCES_NBR; i++)
    {
      if (i == VL53L8A1_DEV_CENTER) continue; 
      if (ToF_Present[i] != 1) continue;

      VL53L8A1_RANGING_SENSOR_ConfigProfile(i, &Profile);
      status = VL53L8A1_RANGING_SENSOR_Start(i, RS_MODE_BLOCKING_CONTINUOUS);
      
      if (status != BSP_ERROR_NONE) {
        printf("Sensor %d Start Failed! Status: %ld\n", i, status);
      }
    }
    
    printf("Waiting for sensor stability (3s)...\n");
    HAL_Delay(3000); 
    printf("System Ready. Continuous Scanning Started.\n");
    
    sensors_started = 1; // ?????????
    return; // ?????????????????? main ???
  }

  // --- 2. ????????? (???? main ????????????????????? while(1)) ---
  
  // ??????????????????
  if (VL53L8A1_RANGING_SENSOR_GetDistance(VL53L8A1_DEV_LEFT, &Result_L) == BSP_ERROR_NONE) 
  {
    has_L = 1;
  }

  // ?????????????????
  if (VL53L8A1_RANGING_SENSOR_GetDistance(VL53L8A1_DEV_RIGHT, &Result_R) == BSP_ERROR_NONE) 
  {
    has_R = 1;
  }

  // --- 3. ???????????? ---
  // ?????????????????????????????????
  if (has_L && has_R) 
  {
    // 如果尚未校准，打印当前采集的空桥架数据给用户复制
    /*
    if (Is_Calibrated == 0)
    {
        static uint8_t calib_cnt = 0;
        static int32_t sum_base_L[64] = {0};
        static int32_t sum_base_R[64] = {0};

        calib_cnt++;
        for(int i = 0; i < 64; i++)
        {
            if (Result_L.ZoneResult[i].NumberOfTargets > 0) {
                sum_base_L[i] += Result_L.ZoneResult[i].Distance[0];
            } else {
                sum_base_L[i] += 110; // 失效点默认110
            }

            if (Result_R.ZoneResult[i].NumberOfTargets > 0) {
                sum_base_R[i] += Result_R.ZoneResult[i].Distance[0];
            } else {
                sum_base_R[i] += 110; // 失效点默认110
            }
        }
        
        if (calib_cnt % 5 == 0) {
            // printf("Calibrating... %d/20\r\n", calib_cnt);
        }

        if (calib_cnt >= 20)
        {
            // 已获取校准数据屏蔽打印
            Is_Calibrated = 1;
        }
        return;
    }
    */

    // A. ???16?闁跨喐鏋婚幏锟??????
    Process_16Columns_Robust(&Result_L, &Result_R, feature_columns);
    
    // B. ????????????
    float saturation_val = Calculate_Tray_Saturation(feature_columns);
    
    // C. ???????????????? sat???? main.c ??????????????
    sat = saturation_val; 

    // D. ?????????? (??????闁跨喐鏋婚幏锟??)
    // printf("\033[H"); // ANSI ????????????????
    // printf("=== Tray Monitoring System ===\n");
    // printf("Saturation: %.2f%%  |  Max Height: %.1f mm\n", saturation_val, feature_columns[8]);
    
    // E. ??????????
    // print_compensated_height_matrix(&Result_L, &Result_R); 
    
    // F. ?????????? (?? Python ?? ???????)
    // Serial_Output_For_Python(feature_columns, saturation_val);
  }

  // ??????????????????? main.c ?? while(1) 
  // ???????????闁跨喐鏋婚幏锟?????????????????????
}



static void print_merged_result(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R)
{
  int8_t row, col;
  uint8_t zones_per_line = 8; // 8x8 ?????? 8

  // 1. ?????????????? (16?闁跨喐鏋婚幏锟?)
  for (col = 0; col < zones_per_line * 2; col++) printf("------");
  printf("--\n");

  // 2. ???闁跨喐鏋婚幏锟??????
  for (row = 0; row < zones_per_line; row++)
  {
    // --- ????????(L)??????? ---
    for (col = (zones_per_line - 1); col >= 0; col--)
    {
      uint8_t zone_idx = (row * zones_per_line) + col;
      if (L->ZoneResult[zone_idx].NumberOfTargets > 0)
        printf("%4ld ", (long)L->ZoneResult[zone_idx].Distance[0]);
      else
        printf("   X ");
    }

    // --- ???????? ---
    printf(" | ");

    // --- ??????????(R)??????? ---
    for (col = (zones_per_line - 1); col >= 0; col--)
    {
      uint8_t zone_idx = (row * zones_per_line) + col;
      if (R->ZoneResult[zone_idx].NumberOfTargets > 0)
        printf("%4ld ", (long)R->ZoneResult[zone_idx].Distance[0]);
      else
        printf("   X ");
    }
    printf("\n");
  }

  // 3. ?????????????
  for (col = 0; col < zones_per_line * 2; col++) printf("------");
  printf("--\n");
}

/**
 * @brief ??????????????????Base - Raw??* Cos
 * ???????????????????????????? 0
 */
static void print_compensated_height_matrix(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R)
{
    int8_t row, col;
    uint8_t zones_per_line = 8;

    printf("\n--- Compensated Height Map (LEFT | RIGHT) [Unit: mm] ---\n");
    for (col = 0; col < zones_per_line * 2; col++) printf("-----");
    printf("\n");

    for (row = 0; row < zones_per_line; row++)
    {
        // --- ??????????? (???????????????????闁跨喐鏋婚幏锟? ---
        for (col = (zones_per_line - 1); col >= 0; col--)
        {
            uint8_t idx = (row * zones_per_line) + col;
            int16_t diff = BaseMap_L[idx] - L->ZoneResult[idx].Distance[0];
            float h = (diff > 0) ? (float)diff * CosMap[idx] : 0; // ??????
            
            // ????????闁跨喐鏋婚幏锟?????? X
            if (L->ZoneResult[idx].NumberOfTargets > 0)
                printf("%3.0f  ", h);
            else
                printf("  X  ");
        }

        printf(" | ");

        // --- ????????????? ---
        for (col = (zones_per_line - 1); col >= 0; col--)
        {
            uint8_t idx = (row * zones_per_line) + col;
            int16_t diff = BaseMap_R[idx] - R->ZoneResult[idx].Distance[0];
            float h = (diff > 0) ? (float)diff * CosMap[idx] : 0;
            
            if (R->ZoneResult[idx].NumberOfTargets > 0)
                printf("%3.0f  ", h);
            else
                printf("  X  ");
        }
        printf("\n");
    }

    for (col = 0; col < zones_per_line * 2; col++) printf("-----");
    printf("\n");
}


static void print_result(RANGING_SENSOR_Result_t *Result)
{
  int8_t i;
  int8_t j;
  int8_t k;
  int8_t l;
  uint8_t zones_per_line;

  zones_per_line = ((Profile.RangingProfile == RS_PROFILE_8x8_AUTONOMOUS) ||
                    (Profile.RangingProfile == RS_PROFILE_8x8_CONTINUOUS)) ? 8 : 4;

  printf("Cell Format :\n\n");
  for (l = 0; l < RANGING_SENSOR_NB_TARGET_PER_ZONE; l++)
  {
    printf(" \033[38;5;10m%20s\033[0m : %20s\n", "Distance [mm]", "Status");
    if ((Profile.EnableAmbient != 0) || (Profile.EnableSignal != 0))
    {
      printf(" %20s : %20s\n", "Signal [kcps/spad]", "Ambient [kcps/spad]");
    }
  }

  printf("\n\n");

  for (j = 0; j < Result->NumberOfZones; j += zones_per_line)
  {
    for (i = 0; i < zones_per_line; i++) /* number of zones per line */
    {
      printf(" -----------------");
    }
    printf("\n");

    for (i = 0; i < zones_per_line; i++)
    {
      printf("|                 ");
    }
    printf("|\n");

    for (l = 0; l < RANGING_SENSOR_NB_TARGET_PER_ZONE; l++)
    {
      /* Print distance and status */
      for (k = (zones_per_line - 1); k >= 0; k--)
      {
        if (Result->ZoneResult[j + k].NumberOfTargets > 0)
          printf("| \033[38;5;10m%5ld\033[0m  :  %5ld ",
                 (long)Result->ZoneResult[j + k].Distance[l],
                 (long)Result->ZoneResult[j + k].Status[l]);
        else
          printf("| %5s  :  %5s ", "X", "X");
      }
      printf("|\n");

      if ((Profile.EnableAmbient != 0) || (Profile.EnableSignal != 0))
      {
        /* Print Signal and Ambient */
        for (k = (zones_per_line - 1); k >= 0; k--)
        {
          if (Result->ZoneResult[j + k].NumberOfTargets > 0)
          {
            if (Profile.EnableSignal != 0)
            {
              printf("| %5ld  :  ", (long)Result->ZoneResult[j + k].Signal[l]);
            }
            else
              printf("| %5s  :  ", "X");

            if (Profile.EnableAmbient != 0)
            {
              printf("%5ld ", (long)Result->ZoneResult[j + k].Ambient[l]);
            }
            else
              printf("%5s ", "X");
          }
          else
            printf("| %5s  :  %5s ", "X", "X");
        }
        printf("|\n");
      }
    }
  }

  for (i = 0; i < zones_per_line; i++)
  {
    printf(" -----------------");
  }
  printf("\n");
}

static void write_lowpower_pin(uint8_t device, GPIO_PinState pin_state)
{
  switch (device)
  {
//    case VL53L8A1_DEV_CENTER:
//      HAL_GPIO_WritePin(VL53L8A1_LPn_C_PORT, VL53L8A1_LPn_C_PIN, pin_state);
//      break;

    case VL53L8A1_DEV_LEFT:
      HAL_GPIO_WritePin(VL53L8A1_LPn_L_PORT, VL53L8A1_LPn_L_PIN, pin_state);
      break;

    case VL53L8A1_DEV_RIGHT:
      HAL_GPIO_WritePin(VL53L8A1_LPn_R_PORT, VL53L8A1_LPn_R_PIN, pin_state);
      break;

    default:
      break;
  }
}

static void reset_all_sensors(void)
{
//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_C_PORT, VL53L8A1_PWR_EN_C_PIN, GPIO_PIN_RESET);
//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_L_PORT, VL53L8A1_PWR_EN_L_PIN, GPIO_PIN_RESET);
//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_R_PORT, VL53L8A1_PWR_EN_R_PIN, GPIO_PIN_RESET);
//  HAL_Delay(2);

//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_C_PORT, VL53L8A1_PWR_EN_C_PIN, GPIO_PIN_SET);
//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_L_PORT, VL53L8A1_PWR_EN_L_PIN, GPIO_PIN_SET);
//  HAL_GPIO_WritePin(VL53L8A1_PWR_EN_R_PORT, VL53L8A1_PWR_EN_R_PIN, GPIO_PIN_SET);
//  HAL_Delay(2);

//  HAL_GPIO_WritePin(VL53L8A1_LPn_C_PORT, VL53L8A1_LPn_C_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(VL53L8A1_LPn_L_PORT, VL53L8A1_LPn_L_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(VL53L8A1_LPn_R_PORT, VL53L8A1_LPn_R_PIN, GPIO_PIN_RESET);
  HAL_Delay(2);

//  HAL_GPIO_WritePin(VL53L8A1_LPn_C_PORT, VL53L8A1_LPn_C_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(VL53L8A1_LPn_L_PORT, VL53L8A1_LPn_L_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(VL53L8A1_LPn_R_PORT, VL53L8A1_LPn_R_PIN, GPIO_PIN_SET);
  HAL_Delay(2);
}
//////////////////////////////////////////////////////////////////////////////??????????

/* ???????????????????8????????? */
static void _sort_8(int16_t *arr) 
{
    int16_t temp;
    for (int i = 0; i < 7; i++) 
	{
        for (int j = 0; j < 7 - i; j++) 
		{
            if (arr[j] > arr[j + 1]) 
			{
                temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
}


void Process_16Columns_Robust(RANGING_SENSOR_Result_t *L, RANGING_SENSOR_Result_t *R, float *out_heights)
{
    int16_t col_buffer[8];
    uint8_t zones_per_line = 8;

    // ????16?? (0-7???????, 8-15?????????)
    for (int col = 0; col < 16; col++) 
    {
        // 1. ??????????????????8????
        for (int row = 0; row < 8; row++) 
        {
            int zone_idx = (row * zones_per_line) + (col % 8);
            int16_t raw_dist, base_dist;

            if (col < 8) { // ????
                raw_dist = L->ZoneResult[zone_idx].Distance[0];
                base_dist = BaseMap_L[zone_idx];
            } else { // ???
                raw_dist = R->ZoneResult[zone_idx].Distance[0];
                base_dist = BaseMap_R[zone_idx];
            }

            // --- ???????? ---
            // 1.1 ??????????????????
            int16_t diff = base_dist - raw_dist;
            if (diff < 0) diff = 0; 

            // 1.2 ?????????????????? = ???????? * cos(theta)
            // ????????? CosMap ????
            float corrected_h = (float)diff * CosMap[zone_idx];
            
            // 1.3 ????????闁跨喐鏋婚幏锟???????
            col_buffer[row] = (int16_t)corrected_h;
            // --- ????????? ---
        }

        // 2. ??????
        _sort_8(col_buffer);

        // 3. ???????????闁跨喐鏋婚幏锟?4??????????
        float robust_avg = (col_buffer[2] + col_buffer[3] + col_buffer[4] + col_buffer[5]) / 4.0f;
        
        out_heights[col] = robust_avg;
    }
}

float Calculate_Tray_Saturation(float *col_heights)
{
    float current_area = 0;
    float col_width = 12.5f;   // 闁跨喎褰ㄩ崠鈩冨 12.5mm
    float max_height = 100.0f; // 闁跨喕鍓奸弸鍫曠彯鐠佽瀚?100mm
    float total_tray_area = 200.0f * 100.0f; // 闁跨喕鍓奸弸鑸垫灮閹风兘鏁撻弬銈嗗闁跨噦鎷?20000 mm^2

    for (int i = 0; i < 16; i++) {
        // 闁跨喐鏋婚幏鐑芥晸婵劕缍嬮崜宥夋晸閸欘偊鐝拋瑙勫鎼存棃鏁撴笟銉╂交閹风兘鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸閿燂拷
        float h = col_heights[i];
        if (h > max_height) h = max_height;
        current_area += (h * col_width);
    }

    // 闁跨喐鏋婚幏宄伴挬闁跨喐鏋婚幏鐑芥晸閺傘倖瀚瑰Ο锟犳晸閺傘倖瀚归柨鐔兼應绾板瀚归崢鐔奉潗闁跨喐鏋婚幏鐑芥晸閺傘倖瀚归柨鐔告灮閹风兘鏁撻柊闈涘閿濆繑瀚?闁跨喐鏋婚幏锟?
    float raw_saturation = (current_area / total_tray_area) * 100.0f;

    // --- 闁跨喐鏋婚幏閿嬧偓渚€鏁撻弬銈嗗闂呮瑩鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸婵劖纭?---
    // 闁跨喐鏋婚幏鐑芥晸閺傘倖瀚圭€圭偤鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸閺傘倖瀚归柨鐔告灮閹风兘鏁撻惃鍡氼嚋閹风兘鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸闁炬澘鐖㈢喊澶嬪闁跨喐鏋婚幏鐑芥闁跨喐鏋婚幏鐑芥晸闁炬壆娈戠拠褎瀚归柨鐔告灮閹峰嘲浜搁柨鐔告灮閹凤拷
    float c_factor = 0.002f; // 闁跨喐鏋婚幏鐑芥晸閺傘倖瀚归弬婊堟晸閺傘倖瀚归柨鐔告灮閹风兘鏁撻弬銈嗗 c闁跨喐鏋婚幏鐑芥晸缂傛挳娼婚幏鐑芥晸閺傘倖瀚圭€圭偤鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸閺傘倖瀚归弽鈥冲櫙
    float k = 1.0f - c_factor * raw_saturation; // 闁跨喐鏋婚幏閿嬧偓渚€鏁撻弬銈嗗闂呮瑩鏁撻弬銈嗗闁跨喐鏋婚幏椋庨兇闁跨喐鏋婚幏锟?
    
    // 闁跨喓顏弬銈嗗缁撅箓鏁撻弬銈嗗閺嶏繝鏁撻弬銈嗗
    if (k < 0.5f) k = 0.5f;
    if (k > 1.0f) k = 1.0f;

    // 闁跨喐鏋婚幏鐑芥晸閹搭亣顔愰幏閿嬧偓渚€鏁撻弬銈嗗闁跨喐鏋婚幏鐑芥晸閺傘倖瀚归柨鐔虹哺绾板瀚归弮鍫曟晸閺傘倖瀚归幎鏇㈡晸閿燂拷
    return raw_saturation * k;
}

// ??????????闁跨喐鏋婚幏锟???????闁跨喐鏋婚幏锟?????
void Serial_Output_For_Python(float *cols, float sat) 
{
    // ???????? @DATA ???? Python ?????????????
    printf("@DATA:"); 
    for(int i = 0; i < 16; i++) 
    {
        printf("%.1f,", cols[i]);
    }
    printf("%.2f\n", sat); // ??闁跨喐鏋婚幏锟????
}


#ifdef __cplusplus
}
#endif
    float col_width = 12.5f;   // 闁跨喎褰ㄩ崠鈩冨 12.5mm
    float max_height = 100.0f; // 闁跨喕鍓奸弸鍫曠彯鐠佽瀚?100mm
    float total_tray_area = 200.0f * 100.0f; // 闁跨喕鍓奸弸鑸垫灮閹风兘鏁撻弬銈嗗闁跨噦鎷?20000 mm^2

