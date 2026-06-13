/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "dma.h"
#include "usart.h"
#include "gpio.h"
#include "app_tof.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

// 用于 printf 重定向到串口 1 (调试用)
#ifdef __GNUC__
#define PUTCHAR_PROTOTYPE int __io_putchar(int ch)
#else
#define PUTCHAR_PROTOTYPE int fputc(int ch, FILE *f)
#endif
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */


extern UART_HandleTypeDef huart2; // 声明串口2
extern DMA_HandleTypeDef hdma_usart2_rx;
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
// DMA 缓冲区
#define RX_BUF_SIZE 512
uint8_t rx_buffer[RX_BUF_SIZE];    // DMA 原始缓冲区
uint8_t process_buf[RX_BUF_SIZE];  // 数据处理缓冲区
volatile uint16_t rx_len = 0;      // 接收到的数据长度
volatile uint8_t rx_flag = 0;      // 接收完成标志

double sat = 0;
// 你的热点和云平台信息
#define WIFI_SSID     "Aurora"
#define WIFI_PWD      "yt220247"

// ---- OneNet MQTT 参数设置 ----
#define ONENET_MQTT_IP    "mqtts.heclouds.com"
#define ONENET_MQTT_PORT  1883
#define ONENET_PROJ_ID    "IqV8M48sQQ"                                // MQTT Username
#define ONENET_DEV_NAME   "Saturation_Detection"                      // MQTT Client ID
#define ONENET_TOKEN      "version=2018-10-31&res=products%2FIqV8M48sQQ%2Fdevices%2FSaturation_Detection&et=2058447118&method=md5&sign=rzM7OnlFyCMOexl5ixFGYQ%3D%3D" // MQTT Password
// 您的物模型上报Topic
#define ONENET_PUB_TOPIC  "$sys/IqV8M48sQQ/Saturation_Detection/thing/property/post"

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

uint8_t ESP8266_Send_Cmd(char *cmd, char *reply, uint16_t timeout);
void ESP8266_Init_Cloud(void);
void Cloud_Upload_Saturation(double saturation);
void MQTT_Connect(void);
void MQTT_Publish(double saturation);
void MQTT_Disconnect(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_UART4_Init();
  MX_USART2_UART_Init();
  MX_USART3_UART_Init();

  /* USER CODE BEGIN 2 */
// --- 步骤 1: 等待电压稳定 ---
  HAL_Delay(500); // 等待串口1电平稳定
  printf("\r\n\r\n=== Power On ===\r\n");
  printf("System Initializing...\r\n");

// --- 步骤 2: 初始化传感器 ---
  // 注意：如果传感器依然 Init 1 failed，请检查供电或 I2C 线是否太长
  MX_TOF_Init();

// --- 步骤 3: 给 ESP8266 准备时间 ---
  printf("Waiting for ESP8266 to boot...\r\n");
  HAL_Delay(3000); // 必须给 WiFi 模块留出启动时间
	
// 3. 关键：在开启 WiFi 接收前，彻底清空一次串口 2 的硬件寄存器
  HAL_UART_DMAStop(&huart2);
  __HAL_UART_CLEAR_FLAG(&huart2, UART_FLAG_ORE | UART_FLAG_NE | UART_FLAG_FE | UART_FLAG_PE);
  __HAL_UART_SEND_REQ(&huart2, UART_RXDATA_FLUSH_REQUEST);
  
  // 4. 开启 DMA 接收（只开这一次，后续除非报错否则不关）
  memset(rx_buffer, 0, RX_BUF_SIZE);
  HAL_UARTEx_ReceiveToIdle_DMA(&huart2, rx_buffer, RX_BUF_SIZE);
  // 注意：下面这行必须确保 hdma_usart2_rx 名字没错，或者直接用 huart2.hdmarx
  if(huart2.hdmarx != NULL) 
  {
      __HAL_DMA_DISABLE_IT(huart2.hdmarx, DMA_IT_HT);
  }

  printf("Connecting to Cloud...\r\n");
  ESP8266_Init_Cloud();

  printf("System Ready.\r\n");
  
  double current_saturation = 0;
  uint32_t last_upload_time = HAL_GetTick(); // 初始化时间戳

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

  MX_TOF_Process();
	  // 修正：实时获取最新的饱和度数据
    current_saturation = sat;
// 检查时间：确保 HAL_GetTick() 正常工作
    if (HAL_GetTick() - last_upload_time > 3000)
    {
      // 强制在串口打印一下，确认逻辑进到了这里
        printf("\r\n[Internal] Triggering Upload... Current Sat: %.2f\r\n", current_saturation);
        Cloud_Upload_Saturation(current_saturation);
      last_upload_time = HAL_GetTick();
    }
	// 检查是否收到云端下发的数据（控制指令）
    if (rx_flag)
    {
      printf("Received from Cloud: %s\r\n", process_buf);
      
      // 解析示例：如果收到 "LED_ON"
      if (strstr((char*)process_buf, "LED_ON")) 
	  {
          // HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_SET);
      }

      rx_flag = 0; // 清除标志
    }
	HAL_Delay(10);
    /* USER CODE BEGIN 3 */
  }
  

  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV1;
  RCC_OscInitStruct.PLL.PLLN = 42;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

uint8_t ESP8266_Send_Cmd(char *cmd, char *reply, uint16_t timeout)
{
    rx_flag = 0;
    memset(process_buf, 0, RX_BUF_SIZE);
    
    // 每次发送前清除溢出错误标志，否则串口会卡死不接收
    __HAL_UART_CLEAR_OREFLAG(&huart2); 

    // 发送
    HAL_UART_Transmit(&huart2, (uint8_t*)cmd, strlen(cmd), 100);
    HAL_UART_Transmit(&huart2, (uint8_t*)"\r\n", 2, 100);
    
    uint32_t start_time = HAL_GetTick();
    while (HAL_GetTick() - start_time < timeout)
    {
        if (rx_flag) 
        {
            // 只要有数据就打印，如果打印出乱码，说明波特率不对
            printf("Module Response: %s\r\n", process_buf);
            
            if (strstr((char*)process_buf, reply)) return 0; // 匹配成功
            rx_flag = 0; // 不是想要的回复，继续等待直到超时
        }
    }
    printf("Wait for [%s] Timeout! Last Buffer: %s\r\n", reply, process_buf);
    return 1; 
}

// 初始化序列 (修改为原子ESP8266通过TCP串口透传直发MQTT报文)
void ESP8266_Init_Cloud(void)
{
    char cmd[256];
    uint8_t retry = 0;
	
    printf("1. Testing AT...\r\n");
    while(ESP8266_Send_Cmd("AT", "OK", 1000)) 
	{
        retry++;
        if(retry > 5) 
		{
            printf("Error: ESP8266 No Response!\r\n");
            return; 
        }
        HAL_Delay(500);
    }

    printf("2. Setting Station Mode...\r\n");
    ESP8266_Send_Cmd("AT+CWMODE=1", "OK", 1000);

    printf("3. Connecting to WiFi: %s...\r\n", WIFI_SSID);
    sprintf(cmd, "AT+CWJAP=\"%s\",\"%s\"", WIFI_SSID, WIFI_PWD);
    while(ESP8266_Send_Cmd(cmd, "WIFI GOT IP", 8000));

    // *重要*：透传模式必须建立在单连接模式上 (CIPMUX=0)
    printf("3.5 Setting Single Connection Mode...\r\n");
    ESP8266_Send_Cmd("AT+CIPMUX=0", "OK", 1000);

    // 使用普通的 TCP 连接连接 OneNet (1883)
    printf("4. Connecting to OneNet TCP Server...\r\n");
    sprintf(cmd, "AT+CIPSTART=\"TCP\",\"%s\",%d", ONENET_MQTT_IP, ONENET_MQTT_PORT);
    if(ESP8266_Send_Cmd(cmd, "OK", 8000) != 0) 
    {
        printf("TCP Connection Failed! Retrying...\r\n");
        HAL_Delay(2000);
    }
    
    // **极其关键的修复**：TCP 刚连上时模块非常繁忙，此时立即发 CIPSEND 会被忽略并提示 busy p...
    printf("Waiting for TCP connection to stabilize...\r\n");
    HAL_Delay(1500); 
    rx_flag = 0; // 清除之前所有的干扰数据
    
    // 发送 MQTT CONNECT 报文
    printf("5. Sending MQTT CONNECT Packet...\r\n");
    MQTT_Connect();
    HAL_Delay(2000); // 给点时间给服务器返回 CONNACK

    printf("Cloud Connect Initialized!\r\n");
}

// 封装发送 MQTT 连接报文
void MQTT_Connect(void)
{
    uint8_t buf[256];
    uint16_t idx = 0;
    
    // 固定报头 10
    buf[idx++] = 0x10;
    
    // 计算 Remaining Length
    uint16_t clientIdLen = strlen(ONENET_DEV_NAME);
    uint16_t usernameLen = strlen(ONENET_PROJ_ID);
    uint16_t passwordLen = strlen(ONENET_TOKEN);
    uint32_t remainLen = 10 + 2 + clientIdLen + 2 + usernameLen + 2 + passwordLen;
    // 剩余长度编码算法
    do {
        uint8_t encodedByte = remainLen % 128;
        remainLen = remainLen / 128;
        if(remainLen > 0) encodedByte |= 128;
        buf[idx++] = encodedByte;
    } while(remainLen > 0);
    
    // 可变报头: 协议名
    buf[idx++] = 0x00; buf[idx++] = 0x04;
    buf[idx++] = 'M'; buf[idx++] = 'Q'; buf[idx++] = 'T'; buf[idx++] = 'T';
    buf[idx++] = 0x04; // 协议级别 v3.1.1
    // OneNet MQTT连接标志位应该为 0xC2 (Clean Session=1, Username=1, Password=1)
    buf[idx++] = 0xC2; 
    buf[idx++] = 0x00; buf[idx++] = 0x1E; // Keep Alive (30s)
    
    // Payload: Client ID
    buf[idx++] = clientIdLen >> 8; buf[idx++] = clientIdLen & 0xFF;
    memcpy(&buf[idx], ONENET_DEV_NAME, clientIdLen); idx += clientIdLen;
    
    // Payload: Username (产品ID)
    buf[idx++] = usernameLen >> 8; buf[idx++] = usernameLen & 0xFF;
    memcpy(&buf[idx], ONENET_PROJ_ID, usernameLen); idx += usernameLen;
    
    // Payload: Password (鉴权Token)
    buf[idx++] = passwordLen >> 8; buf[idx++] = passwordLen & 0xFF;
    memcpy(&buf[idx], ONENET_TOKEN, passwordLen); idx += passwordLen;
    
    // 使用 AT+CIPSEND=<length> 发送连接报文
    char send_cmd[32];
    sprintf(send_cmd, "AT+CIPSEND=%d", idx);
    
    // 给系统留一点缓冲区重置时间
    HAL_Delay(200); 
    if (ESP8266_Send_Cmd(send_cmd, ">", 3000) == 0 || strstr((char*)process_buf, ">")) {
        HAL_UART_Transmit(&huart2, buf, idx, 2000);
        printf("MQTT Connect Packet Sent. Len: %d\r\n", idx);
    } else {
        printf("MQTT Connect: AT+CIPSEND Timeout!\r\n");
    }
}

// 封装发送 MQTT Publish 报文
void MQTT_Publish(double saturation)
{
    uint8_t buf[256];
    char payload[128];
    uint16_t idx = 0;
    
    // Fixed string format with proper backslashes, matching CSDN article format:
    // "{\"id\":\"1\",\"version\":\"1.0\",\"params\":{\"Saturation\":{\"value\":%.2f}}}"
    sprintf(payload, "{\"id\":\"1\",\"version\":\"1.0\",\"params\":{\"Saturation\":{\"value\":%.2f}}}", saturation);
    uint16_t payloadLen = strlen(payload);
    uint16_t topicLen = strlen(ONENET_PUB_TOPIC);
    
    // 固定报头 30
    buf[idx++] = 0x30; // QoS = 0
    
    // Remaining Length
    uint32_t remainLen = 2 + topicLen + payloadLen;
    do {
        uint8_t encodedByte = remainLen % 128;
        remainLen = remainLen / 128;
        if(remainLen > 0) encodedByte |= 128;
        buf[idx++] = encodedByte;
    } while(remainLen > 0);
    
    // 可变报头: Topic
    buf[idx++] = topicLen >> 8; buf[idx++] = topicLen & 0xFF;
    memcpy(&buf[idx], ONENET_PUB_TOPIC, topicLen); idx += topicLen;
    
    // Payload
    memcpy(&buf[idx], payload, payloadLen); idx += payloadLen;
    
    // 使用 AT+CIPSEND=<length> 发送数据报文
    char send_cmd[32];
    sprintf(send_cmd, "AT+CIPSEND=%d", idx);
    if (ESP8266_Send_Cmd(send_cmd, ">", 2000) == 0) {
        HAL_UART_Transmit(&huart2, buf, idx, 1000);
        printf("MQTT Publish Packet Sent.\r\n");
    } else {
        printf("MQTT Publish: AT+CIPSEND Timeout!\r\n");
    }
}

void Cloud_Upload_Saturation(double saturation)
{
    printf("--> Sending MQTT Publish packet: %.2f\r\n", saturation);
    MQTT_Publish(saturation);
}

// 封装发送 MQTT 断开报文 (用于主动断开连接)
void MQTT_Disconnect(void)
{
    uint8_t buf[2];
    buf[0] = 0xE0; // DISCONNECT 固定报头 (1110 0000)
    buf[1] = 0x00; // Remaining Length: 0
    
    char send_cmd[32];
    sprintf(send_cmd, "AT+CIPSEND=%d", 2);
    if (ESP8266_Send_Cmd(send_cmd, ">", 2000) == 0) {
        HAL_UART_Transmit(&huart2, buf, 2, 1000);
        printf("MQTT Disconnect Packet Sent.\r\n");
    } else {
        printf("MQTT Disconnect: AT+CIPSEND Timeout!\r\n");
    }
}
/* ---------------------------------------------------------------------------
 * 中断回调与重定向
 * --------------------------------------------------------------------------- */

// 串口接收中断回调 (DMA 空闲中断触发)
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart->Instance == USART2)
    {
        memcpy(process_buf, rx_buffer, Size);
        process_buf[Size] = '\0';
        rx_len = Size;
        rx_flag = 1;

        // 重新开启 DMA 接收
        HAL_UARTEx_ReceiveToIdle_DMA(&huart2, rx_buffer, RX_BUF_SIZE);
        __HAL_DMA_DISABLE_IT(&hdma_usart2_rx, DMA_IT_HT);
    }
}

// 新增：串口错误回调函数
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        // 如果发生溢出错误或其它错误，强制重启 DMA 接收
        HAL_UARTEx_ReceiveToIdle_DMA(&huart2, rx_buffer, RX_BUF_SIZE);
        __HAL_DMA_DISABLE_IT(huart2.hdmarx, DMA_IT_HT); 
    }
}

// printf 重定向到串口 1
PUTCHAR_PROTOTYPE
{
  HAL_UART_Transmit(&huart1, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
  return ch;
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
